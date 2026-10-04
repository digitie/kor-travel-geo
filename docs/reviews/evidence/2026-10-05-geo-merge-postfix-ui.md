<!-- SPDX-License-Identifier: GPL-3.0-only -->

# Geo 최종 수정 후보 — 독립 merge post-fix 리뷰 원본

- 실행 ID GEO-MERGE-A-20261005-596b7d1; James (/root/review_ui).
- 시각 2026-10-04 22:47:34~22:52:04 UTC / 2026-10-05 07:47:34~07:52:04 KST.
- 저장소 F:/dev/kor-travel-geo-codex-dagster-common.
- 원 base3f4ddc2dac3f31634a23ef0e9592f419e29e7d14.
- 후속 delta basece82b079619b9db8b8ccbcf540f13e9ab78acc91.
- 실제 immutable candidate596b7d177517f3b53cb811e36720d9af9bba582b.
- Python pinab21cc3b7b77e5e6d6cd277ca64840761fc4d7a4; UI426/dev.3 tarball SHA25603feae21b9e44041b648ba6d0defc3b16b97973ed3c7e70a83b91d279afb2f43 직접 확인.
- **최종 verdict CONDITIONAL**. 기존 source 결함 수정, 새 공통P2 disposition 및 외부 gate는 별도.

## 격리·실제 범위

고정 Git show/diff/archive/rev-parse만 사용하고 /tmp/james-geo-merge-596b7d1 자체 source archive에서 실행했다. 부모 이후 문서/closure commit과 source SHA를 혼동하지 않았다. 상대 보고서·통합 판정은 읽지 않고 source/install/mirror/dirty원본/외부 DB·서비스를 수정하지 않았다. 기존 ext4 Node deps·Python3.12.13 venv를 읽기 재사용했다.

직접 ce82→596b 4파일 제품/test delta와 기존 base 전체 UI·publication 검토 맥락을 확인했다. UI tree가ce82와 동일함을 고정 diff로 확인하고 실제 vendor를 다시 렌더링했다. guard의 두 refresh 분기 전달·별도 radius transaction commit전 검증 및 새 native PG test source를 읽었다.

## EXECUTED

- 기존 소비자+본인 통합/SSR 공격 **51 PASS**. named repository/mobile collapsed headings, snapshot/선택상세/abort, 로그인 status/password/동시 제출, SSR encoded-tab 로컬 redirect, 메뉴 ref/aria/cookie/revocation 및 로그 keyboard region.
- 고정 postload_mv/batch_dag/infra_repo_sql 단위 **78 PASS,1.34초**.
- 본인 기존 radius transaction recorder 공격을 같은 조건으로 재실행했다. 실제 refresh_mv의 첫 MV commit 후 cancel_event set; 다음 radius transaction의 guard가 LoadJobLeaseLostError를 내고 rollback 경로로 종료했다. guard2회/commit1회/radius_commit_after_cancel=false. native PostgreSQL 실행이라고 주장하지 않는다.
- Python pinab21은 본인 common-merge-postfix-ui.md의67건 및 실제 SQLite provider·late-framework 공격으로 독립 확인했다.

## 이전 finding disposition

- G-UI-P2-01/P3-01: FIXED 유지, 동일 UI 공격 PASS.
- G-UI-P1-02의92eb 느린 여러 페이지 문제: FIXED 유지.
- G-PUB-P1-01 / 공통 C-PHASE-P1-01(P1): FIXED. completed cursor 이후 실제 provider 후속 기록은 요청0·태그0.
- G-PUB-P2-01(P2): FIXED(source·독립 recorder). concurrent와swap 양쪽이 radius guard를 전달하고 실제 별도 transaction의 commit 전에 확인한다. 기존 재현에서는 취소 이후 radius commit이 없어졌다. 기존 severity/원문은 보존했다. 실제 PG rollback·동시 lock gate는 본인 NOT_RUN이며 부모의 별도 native evidence 확인이 필요하다.

## 잔여 공통 의존성 P2

고정 pinab21의 본인 신규 **C-MERGE-P2-01**을 소비자 위험으로 참조한다. 위치는 kor-travel-geo-dagster/pyproject.toml:22 및 definitions.py:97의 factory 등록이다. 유효한 늦은 child framework STEP_FAILURE만 있는 실제 이력에서 정상3.1초 RUN_FAILURE/5.1초 STEP 조회가 complete→run→head를 반복하며 요청0인 반면 같은 이력의 빠른 cold scan은 요청1이다. 자세한 exact source line·실제 SQLite 재현·SHA는 common-merge-postfix-ui.md 정본에 있다.

Geo UI의 새P0/P1/P2는 발견하지 않았다. 공통P2 수정·새 pin 또는 owner/task/gate/기한을 갖춘 연기가 필요하며, 이를 소비자 통합 gate와 구분하지 않고 전체 PASS로 표시할 수 없다. 새로운 소비자 고유 ID로 동일 결함을 중복 집계하지 않는다.

## 재현 산출물·명령

- /tmp/james-geo-merge-596b7d1/radius_guard_probe.py SHA25624d08e27b7a9a1a9f2016b151ac9423987b5a53fc621de3aa6ac2f5b65201108.
- 자체 UI 통합 공격은 ce82 원본의12건을 동일 유지하며 동일 common UI vendor를 사용했다.
- source tree와 evidence만의 후속 closure commit은 구분한다. Common full 판정은 공개UI/CSS/Python/runbook 때문에 비면제라는 독립 판단이며, 이 소비자도 사용자 요청의 두 독립 리뷰·live gate 범위에 속한다.

```bash
cd /tmp/james-geo-merge-596b7d1
PYTHONPATH=/tmp/james-geo-merge-596b7d1/src TMPDIR=/tmp TMP=/tmp TEMP=/tmp /home/digitie/dev/kor-travel-geo-codex-dagster-common-test/.venv/bin/python radius_guard_probe.py
PYTHONPATH=/tmp/james-geo-merge-596b7d1/src TMPDIR=/tmp TMP=/tmp TEMP=/tmp KTG_GEOIP_GATE_MODE=off /home/digitie/dev/kor-travel-geo-codex-dagster-common-test/.venv/bin/python -m pytest -q tests/unit/test_postload_mv.py tests/unit/test_batch_dag.py tests/unit/test_infra_repo_sql.py --confcutdir=/tmp/james-geo-merge-596b7d1/tests/unit

cd kor-travel-geo-ui
node /home/digitie/dev/kor-travel-geo-codex-dagster-common-test/kor-travel-geo-ui/node_modules/vitest/vitest.mjs run --config /tmp/james-geo-merge-596b7d1/james.vitest.config.mjs --configLoader native tests/unit/james.integration-attack.test.tsx tests/unit/james.ssr-attack.test.tsx tests/unit/dagster-panel.test.tsx tests/unit/app-shell-drawer.test.tsx tests/unit/auth.test.ts tests/unit/session-revocation.test.ts tests/unit/proxy-gate.test.ts tests/unit/backup-workflow.test.ts
```

## NOT_RUN·최종 판정

실제 PostgreSQL rowlock/commit/rollback·native daemon/provider, 직접 browser/live/키보드 실제 스크롤/픽셀, cleanDocker/전체suite/CI는 수행하지 않았다. 부모 nativePG/브라우저/live 결과를 본인 실행으로 산입하지 않았고 진행 중인 remote build를 완료로 판정하지 않았다.

**CONDITIONAL**. 본인 기존 UI·publication·provider 안전성 지적은 고정 source 및 독립 재현으로 수정 확인했다. 공통pin의 새P2 disposition과 실제PG/live/CI·두 원본 full gate 확인이 남는다.
