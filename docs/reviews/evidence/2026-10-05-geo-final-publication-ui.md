<!-- SPDX-License-Identifier: GPL-3.0-only -->

# Geo 게시 소유권·로그 영역 후속 후보 — 독립 적대 리뷰 원본

- 실행 ID: GEO-PUBLICATION-A-20261005-ce82b07, 리뷰어 James (/root/review_ui).
- 관측: 2026-10-04 22:33:32~22:35:46 UTC / 2026-10-05 07:33:32~07:35:46 KST.
- 원래 base: 3f4ddc2dac3f31634a23ef0e9592f419e29e7d14.
- 후속 delta base: c3011220e26e2a733260f429222eeebdcc459680.
- 실제 immutable candidate: ce82b079619b9db8b8ccbcf540f13e9ab78acc91 (Git rev-parse 확인).
- 공통 UI426/dev.3 동일; 공통 Python3194a0b6c81d64a75dc937f177588a300944b2af pin.
- 최종 판정: **BLOCK**. Geo 신규 P2 및 본인 공통 신규 P1의 소비자 pin이 남는다.

## 격리·범위

고정 Git show/diff/archive의 13파일 delta를 읽었다. 상대 리뷰·통합 판정·journal/closure는 읽지 않았다. source/install/mirror/공유 DB·컨테이너를 변경하지 않았다. 자체 /tmp/james-geo-publication-ce82b07 snapshot에서 ext4 Node dependencies와 Python3.12.13 venv를 읽기만 재사용했다. 단위 실행은 외부 PG/provider 없이 모의 transaction 또는 자체 SQLite 범위였다.

PublicationGuard의 running/executor/owner 조건, parent+child의 정렬된 FOR UPDATE, cancel_event 전후 검사, standalone·batch guard 전달, shadow swap/release activation transaction의 검증 호출, SQL30분 설정, 로그 CSS·region 접근성 및 기존 로그인/메뉴/관측 계약을 검토했다.

## EXECUTED

- 실제 candidate UI/SSR: 기존 30건 + 자체 통합 공격12건 + SSR9건, **51 PASS**. named repository 링크·모바일 collapsed 제목·last snapshot·사용자 두 번째 run 선택/상세·unmount abort·로그인 status/password/동시 제출·쿠키/폐기/origin/rate/ref/aria를 재실행했다.
- 신규 로그 공격: 실제 OpLogGroups의 한글 메시지를 렌더링하고 backup_op 이벤트 로그 region의 tabIndex0·명시적 이름·focus·table class를 확인했다. CSS48rem 최소폭/20rem 메시지폭/24rem 내부 overflow는 고정 source로 확인했다. 실제 픽셀/overflow는 NOT_RUN.
- 고정 tests/unit/test_postload_mv.py + test_batch_dag.py + test_infra_repo_sql.py: **77 PASS, 1.35초**.
- 자체 실제 refresh_mv 호출/async transaction recorder 공격: 첫 MV transaction commit 직후 cancel_event를 설정하여 다음 region_radius_parts transaction이 guard 없이 TRUNCATE/INSERT를 커밋하는 것을 확인했다. DB를 연결하거나 실제 PostgreSQL commit했다고 주장하지 않는다.
- 공통3194 별도 본인 리뷰: **65 PASS,43.72초**, 실제 SQLite provider 후속 기록 공격으로 C-PHASE-P1-01 재현. 원문 common-phase-postfix-ui.md는 변경 없이 유지했다.

## 기존 지적

- G-UI-P2-01/P3-01 CLOSED 유지: named repository 경로 및 collapsed 모바일 그룹 제목의 동일 공격이 통과한다.
- G-UI-P1-02의 이전 Python92eb 느린 유한 페이지 결함은 새 pin의 checkpoint 회귀로 CLOSED. 기존 severity P1과 원문은 변경하지 않았다. 아래 새 완료 phase 결함은 별개의 P1이다.

## G-PUB-P2-01 — 중지 후 serving 반경 테이블 재구축은 게시 guard를 통과하지 않음 (P2)

- 위치: src/kortravelgeo/loaders/postload.py:63,88,92-97.
- 실패 시나리오: guarded MV transaction이 정상 commit된 뒤 API 취소/소유권 회수가 완료되고 cancel_event가 set된다. refresh_mv는 그대로 별도 refresh_region_radius_parts transaction을 실행한다. 해당 함수는 PublicationGuard를 받지 않고 SQL을 전부 실행한 뒤 commit한다.
- 근거: 실제 SQL에는 region_radius_parts TRUNCATE·INSERT가 있고 geometry_repo.py:318,335,349의 온라인 serving 반경 조회가 이 테이블을 소비한다. guard가 보호하는 MV만의 통계나 shadow scratch가 아니다.
- 자체 재현: 실제 refresh_mv(concurrently=True, publication_guard=...)를 transaction recorder로 실행했다. guard는 cancel 이후 호출되면 LoadJobLeaseLostError를 내도록 구성했으나 총1회만 호출되었다. 첫 transaction 정상 commit 직후 event를 set한 뒤 두 번째 transaction은 event=true 상태에서 TRUNCATE·INSERT를 commit했다.
- 관측 출력: publication_guard_calls=1, commit_count=2, radius_commit_after_cancel=true.
- 영향: MV swap/release activation을 막아도 소유권을 잃은 worker가 실제 serving 보조 테이블을 게시할 수 있다. main MV가 이미 정상 게시된 결과라는 점과 구분하며, 이후 별도 변경을 막는 경계가 빠졌다는 finding이다.
- 최소 수정: guarded Dagster 경로에서는 refresh_region_radius_parts에도 optional guard를 전달하고 변경 transaction의 commit 전에 owner/root/cancel 검증을 수행한다. API/CLI 수동 경로의 기본 동작은 유지한다. MV 이후 취소와 radius build 중 취소 모두 rollback/no publish 회귀로 증명한다.
- 폐쇄 조건: 본인 recorder 재현이 commit 대신 LoadJobLeaseLostError/rollback이며 실제 PG에서 serving 테이블 이전값을 보존하는 회귀가 필요하다.

## G-PUB-P1-01 — 완료 phase에서 후속 provider 오류를 승인하는 공통 pin (P1)

- 위치: kor-travel-geo-dagster/pyproject.toml:22; 실제 factory 등록 definitions.py:97.
- 원인/본인 정본 finding: 공통3194 dagster.py:251-255의 C-PHASE-P1-01.
- 실제 SQLite 재현: completed checkpoint 이후 같은 RUN_FAILURE storage ID3를 유지하면서 USER_CODE_ERROR/ValueError STEP_FAILURE를 실제 append하면 resume 요청1·native 억제/pending 쓰기1. 동일 이력 cold scan과 새 RUN_FAILURE ID 대조군은 요청0이다.
- 영향: Geo가 실제 사용하는 backup_verify fallback factory가 provider 실패 자동 반복 금지 계약을 깨뜨릴 수 있다. 이 보고서가 Geo production daemon을 직접 재현한 것은 아니다.
- 최소 수정/폐쇄: 공통에서 완료 검증 재사용을 실제 step/event tail 불변성에 묶거나 새 이력을 안전하게 검사하고, 유한 지연 진행 회귀와 late-provider 거부 회귀가 함께 통과한 새 SHA로 소비자 pin을 갱신한다.

## 재현 산출물·명령

- /tmp/james-geo-publication-ce82b07/radius_guard_probe.py
  SHA256 a5dff024e4470c81df59f46355456babb6bfe348dabeaaf117eb7c7e3eeeca09.
- 자체 UI 통합 공격 SHA256 e2030ef23204fadd5a7c69a4446c86c6463c8e2e3e630f596ec28befc64e834c.
- 자체 SSR 공격 SHA256 7c7b6d3d2f8910c5321c70144bbaaffbd443832634296570731a9918f8f133fd.
- 공통 실제 late-provider 재현: /tmp/james-common-phase-3194a0b/late_provider_probe.py, SHA256 2ccbf710f40dd3ddd1d20b43a8efe314bb4da61ad58b3e025f1c1f556cf3cb88.

```bash
cd /tmp/james-geo-publication-ce82b07
PYTHONPATH=/tmp/james-geo-publication-ce82b07/src TMPDIR=/tmp TMP=/tmp TEMP=/tmp /home/digitie/dev/kor-travel-geo-codex-dagster-common-test/.venv/bin/python radius_guard_probe.py
PYTHONPATH=/tmp/james-geo-publication-ce82b07/src TMPDIR=/tmp TMP=/tmp TEMP=/tmp KTG_GEOIP_GATE_MODE=off /home/digitie/dev/kor-travel-geo-codex-dagster-common-test/.venv/bin/python -m pytest -q tests/unit/test_postload_mv.py tests/unit/test_batch_dag.py tests/unit/test_infra_repo_sql.py --confcutdir=/tmp/james-geo-publication-ce82b07/tests/unit

cd kor-travel-geo-ui
node /home/digitie/dev/kor-travel-geo-codex-dagster-common-test/kor-travel-geo-ui/node_modules/vitest/vitest.mjs run --config /tmp/james-geo-publication-ce82b07/james.vitest.config.mjs --configLoader native tests/unit/james.integration-attack.test.tsx tests/unit/james.ssr-attack.test.tsx tests/unit/dagster-panel.test.tsx tests/unit/app-shell-drawer.test.tsx tests/unit/auth.test.ts tests/unit/session-revocation.test.ts tests/unit/proxy-gate.test.ts tests/unit/backup-workflow.test.ts
```

## NOT_RUN·한계

직접 live CUA/Chromium/Firefox/픽셀·키보드 실제 스크롤, 실제 PG의 MV/row lock·동시 취소·release rollback, clean Docker/Node build/전체 Python/CI는 수행하지 않았다. 부모 PG15PASS와 브라우저12checks는 본인 직접 실행으로 산입하지 않았고 진행 중인 최종 remote build/live를 완료로 판정하지 않았다. recorder는 actual function 호출순서/guard 누락을 증명하며 PostgreSQL lock·rollback 실효는 별도 native 회귀가 필요하다.

## 최종 판정

**BLOCK**. UI 의미·접근성 단위 검증은 통과했으며 이전 UI 지적은 폐쇄 유지한다. 별도 serving 반경 게시 경로의 guard 누락 P2와 새 공통 completed checkpoint P1이 남는다.
