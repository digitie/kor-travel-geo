<!-- SPDX-FileCopyrightText: 2026 digitie -->
<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# Geo 공용 UI 채택 — 독립 적대 리뷰 원본

- 실행 ID: `GEO-UI-A-20261005-9db3918`.
- 관찰: `2026-10-04 21:28:39~21:39:51 UTC` / `2026-10-05 06:28:39~06:39:51 KST`.
- 저장소: `/mnt/f/dev/kor-travel-geo-codex-dagster-common`.
- 실제 base: `3f4ddc2dac3f31634a23ef0e9592f419e29e7d14`.
- 실제 후보: `9db391807db163ea0eafd09ceb5b434b5870cf47`.
- 공용 UI source: `426de4fbad35282bb558712d922c06268e9aba62`, Python pin: `430a9e9cd5429204579792b1d4f8e399366dcb2f`.
- 격리: Linux Git 고정 객체의 manifest·제품 frontend delta와 API 경계를 검토했다. peer 보고서·통합 판정을 읽지 않았다. geo source/checkout/commit/push/부모 mirror/설치/DB는 변경하지 않았다.
- 실행 snapshot은 고정 Git archive를 `/tmp/james-geo-review-9db391807db1`에 풀고 부모 mirror의 기존 Node 의존성만 재사용했다. UI 구현은 후보 vendor tarball을 별도로 풀어 resolve했다. scratch에서만 회귀 판별용 mutant와 원래 base AppShell을 실행한 후 두 scratch source의 Git blob hash가 후보와 다시 같음을 확인했다.

## 판정

**CONDITIONAL. G-UI-P2-01의 수정 또는 명시적 disposition이 필요하다. G-UI-P3-01은 작은 모바일 표시 회귀다. 새 P0/P1은 확인하지 못했다.**

실제 geo live 및 후보 CI는 진행 중으로 전달됐다. 본 리뷰에서는 완료로 집계하지 않는다.

## Findings

### G-UI-P2-01 — 이름 있는 repository의 스케줄 링크가 다른 repository 주소로 해석된다

- 위치: `kor-travel-geo-ui/components/admin/DagsterPanel.tsx:112`.
- 실패 시나리오: public DTO의 repository가 name=repo, location_name=geo location이고 schedule=hourly다. settings의 `dagster_repository_name`은 기본값 이외 이름도 허용한다(`src/kortravelgeo/settings.py:167`).
- 독립 재현: 실제 geo adapter와 vendor UI를 렌더링해 스케줄을 펼쳤다. 생성 href는 `https://dagster.example/dagster/locations/geo%20location/schedules/hourly`였다. 해당 repository의 주소는 `/locations/repo@geo%20location/schedules/hourly`여야 하므로 DOM assertion이 실패했다.
- 근거: 고정 이미지 버전 Dagster 1.13.24의 공식 [주소 생성기](https://github.com/dagster-io/dagster/blob/1.13.24/js_modules/ui-core/src/workspace/buildRepoAddress.ts)와 [주소 파서](https://github.com/dagster-io/dagster/blob/1.13.24/js_modules/ui-core/src/workspace/repoAddressFromPath.ts)를 대조했다. repository 이름 없는 경로는 __repository__로 파싱된다.
- 영향: named repository 스케줄 상세로 연결되지 않는다. 기본 __repository__에는 이 문제가 없으며 현재 운영 geo가 깨졌다고 주장하지 않는다. 브라우저에서 실제 대상 이동은 NOT_RUN이다.
- 최소 수정: __repository__이면 location만, 그 외에는 repository.name@encodedLocation을 사용하는 Dagster 경로 계약을 적용한다. base path와 schedule encoding을 보존하고 두 repository 종류의 URL 회귀를 추가한다.
- disposition 조건: 고정 후보에서 named/dunder 주소를 확인하거나 owner/task/gate/목표 시점을 명시해 P2를 연기한다.

### G-UI-P3-01 — 데스크톱 접기 설정을 저장하면 모바일 드로어의 그룹 제목도 사라진다

- 위치: `kor-travel-geo-ui/components/layout/AppShell.tsx:319`.
- 실패 시나리오: localStorage `kor-travel-geo:sidebar-collapsed=1`인 상태에서 1023px 이하 드로어를 연다.
- 독립 재현: 실제 AppShell의 matchMedia를 좁은 화면으로 설정하고 저장된 접기 상태에서 메뉴를 열었다. 후보에서는 조회·진단 그룹 제목을 찾는 assertion이 실패했다. 같은 공격에서 base AppShell은 통과했다.
- 원인: collapsed 상태가 viewport와 무관하게 group.label을 undefined로 만든다. 기존 구현은 제목을 유지하고 데스크톱 CSS에서만 숨겼다.
- 영향: 모바일의 시각적 그룹 구분이 없어진다. nav aria-label과 개별 링크 이름은 남으므로 메뉴 접근 자체를 막는 문제로 과장하지 않는다.
- 최소 수정: label을 항상 제공하고 이미 존재하는 데스크톱 media 규칙으로 숨기거나, 모바일에서 collapsed를 적용하지 않는다.
- disposition 조건: desktop 접기→mobile 열기 회귀 또는 작은 표시 회귀의 명시적 수용.

## EXECUTED

- 기존 고정 테스트 6파일, **30 PASS**: DagsterPanel 4, AppShell drawer 8, auth 9, session revocation 4, proxy gate 2, backup workflow 3.
- 자체 공격 최종 10건: **8 PASS / finding 재현 2 FAIL**. 명령은 아래와 같으며 repo source 변경 없이 scratch에서 실행했다.
- PASS 항목: 의미적 outage 뒤 성공 snapshot 유지, unmount의 진행 중 summary 요청 abort, 로그인 503/429/403/401 오류 구분·password 삭제·unsafe next 로컬 경로 보정·password 원문 보존, 동시 제출 단일 호출·예외 상세 비노출, DocumentNavLink의 React19 ref·aria-current·추가 anchor 속성·keydown 전달.
- stalled tag/미확인 schedule/실패 tick DOM assertion은 통과했고 해당 시험의 외부 URL assertion이 G-UI-P2-01로 실패했다.
- stale 검사의 판별성: scratch에서 status 오류 거부만 제거한 mutant는 기존 행 유지 assertion에 실패했다. 후보 구현 복원 후 해당 공격은 PASS다.
- 모바일 제목 검사의 판별성: 후보 FAIL→원래 base AppShell PASS. scratch AppShell은 후보로 복원했다.
- tarball SHA256 확인: UI `03feae21b9e44041b648ba6d0defc3b16b97973ed3c7e70a83b91d279afb2f43`, tokens `554ae3f6a18cbf453130b29f8a2d737ddb880101b55e14535cf8d63174b47505`. UI sha512는 fixed package-lock integrity와 일치한다. 실제 Node v22.22.2, lock/runtime React19.3.0이었다.

```bash
cd /tmp/james-geo-review-9db391807db1/kor-travel-geo-ui
node /home/digitie/dev/kor-travel-geo-codex-dagster-common-test/kor-travel-geo-ui/node_modules/vitest/vitest.mjs run \
  --config james.vitest.config.mjs --configLoader native --maxWorkers 1 --no-file-parallelism \
  tests/unit/james.integration-attack.test.tsx
```

공격 원문 파일 SHA256: `055ef06d78733d32806a8f1d11b697e7e7b8a8c87a3d22ffa7f8191332662c3f`.

하네스 실패도 구분했다. 첫 기존 suite의 1건 실패는 잘못된 cwd의 CSS 경로였고 scratch cwd에서 30 PASS로 해결됐다. 자체 시험 초기에는 미설치 user-event와 beforeEach가 mock 함수를 반환하는 Vitest cleanup 문제가 있었다. fireEvent와 반환 없는 setup으로 수정했다. 제품 finding으로 세지 않았다.

## READ_ONLY·NOT_RUN·한계

- AGENTS/SKILL과 runbook, 구조 문서·ADR-068을 참조했다. 인증 서버의 origin/rate/password/cookie/revocation 경계와 AppShell의 full-document navigation·inert/focus/scroll lock 동작은 유지되는 source를 읽었다. 실제 로그인 쿠키 교환은 NOT_RUN이다.
- GraphQL 활성 NOT_STARTED/QUEUED/STARTING/STARTED/CANCELING, 1000건 상한·중복 제거·4MiB stream 상한·조회 오류 상태와 DTO adapter를 읽었다. 실제 서버의 해당 경계 실행은 NOT_RUN이다.
- geo 실패 확인 mutation·실패 banner·backup artifact·op event 상세의 연결은 기존 4건 DagsterPanel 시험으로 확인했다. 모든 도메인/DB 복구 실행을 검증한 것은 아니다.
- 부모 전달 backend1782 PASS/101 skip, Dagster150 PASS, frontend231 PASS·lint/type/build/doctor90, PG7 PASS는 직접 실행 결과로 계산하지 않는다.
- 직접 production/Docker build·전체 frontend/backend·native Dagster/PG·실제 n150 UI·키보드/viewport/CSS geometry·색 대비는 NOT_RUN이다.
- 50행 DOM과 bounded API 구조를 확인했으나 RSS 개선율·React19 지도 UI 전체 영향은 실측하지 않았다.
- 원본 SHA256은 파일 생성 뒤 별도로 전달한다.
