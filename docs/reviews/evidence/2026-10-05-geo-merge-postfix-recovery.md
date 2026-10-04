# Geo merge 후보 독립 post-fix 기능·복구 리뷰 원문

- 리뷰어: /root/review_recovery_final
- 날짜: 2026-10-05
- repository: /mnt/f/dev/kor-travel-geo-codex-dagster-common
- base: 3f4ddc2dac3f31634a23ef0e9592f419e29e7d14
- immutable source candidate: **596b7d177517f3b53cb811e36720d9af9bba582b**
- fixed common dependency: **ab21cc3b7b77e5e6d6cd277ca64840761fc4d7a4**
- 이전 독립 source: ce82b079619b9db8b8ccbcf540f13e9ab78acc91
- 검토 범위 코드 판정: **PASS**
- 기존 B-P2-01: **FIXED**, 신규 actionable finding: 0건.

## 독립성·고정과 범위

새 source archive를 /tmp/recovery-postfix-independent/geo에 고정했다. common도 새 source archive로 고정했고 Git dependency와 ADR이 동일 common SHA를 참조하는지 확인했다. 후속 문서 HEAD나 원본 미커밋 변경을 검토 source로 섞지 않았다. 기존 AGENTS.md/저장소 SKILL 및 runbook 규칙을 유지하며 ADR-068의 갱신된 transaction 경계를 검토했다.

본인 기존 Python 환경을 실행만 재사용했고 fixed common/src + Geo/src + Geo Dagster/src를 PYTHONPATH에 지정했다. 추가 테스트는 본인 /tmp 사본에서만 작성했다. 원본·제품 source·기존 설치·외부 서비스/DB를 수정하지 않았다. 다른 현행 리뷰어 결과와 부모 journal 판정은 읽지 않았다.

이번 본인 수행 범위는 SQLite와 Fake SQL이다. 실제 PostgreSQL/PostGIS MV rollback/row locking, RustFS, UI/live, 운영 Dagster worker 장애 주입, 설치·전체 회귀·CI는 **NOT_RUN**이다. 부모가 제공한 실제 PG/UI 근거는 본인이 실행한 결과로 주장하거나 합산하지 않는다.

## B-P2-01 closure — 별도 반경 serving transaction의 commit guard

이전에는 guarded MV transaction을 commit한 뒤 region_radius_parts를 별도 transaction으로 TRUNCATE/INSERT하면서 작업 취소·소유권 상실을 검사하지 않았다.

수정 위치: src/kortravelgeo/loaders/postload.py:63–66, :91–94, :98–108. swap/concurrent 두 경로가 PublicationGuard를 실제 refresh_region_radius_parts 호출에 전달한다. 긴 SQL 재생성 후 commit 직전 guard를 같은 connection에서 호출하므로 취소 또는 owner/running 행 상실은 그 transaction을 rollback한다.

본인 test_closure.py::test_radius_cancel_after_mv_commit_closure는 이전과 동일하게 첫 MV transaction commit 직후 cancel_event를 설정했다.

- concurrent/swap 각각 실제 refresh_mv의 후속 호출 경로를 실행했다.
- 실제 region_radius_parts TRUNCATE/INSERT 문자열은 발행되지만 해당 transaction은 **rollback**한다.
- 이전에 commit된 MV transaction은 **commit** 상태로 남는다.
- 취소 뒤 GeoCacheRepository.clear에 도달하지 않는다.
- swap build 단계와 swap 자체는 이 특정 routing 시험에서 Fake로 치환했다. 실제 shadow_swap_mv와 guard의 동일 transaction rollback은 별도의 기존 본인 test_independent 시험을 새 source에서 재실행했다.

본인 test_actual_radius_transaction_guard의 valid/lost-owner/cancel-during 3개 사례도 실제 refresh_region_radius_parts 함수를 호출했다. INSERT 수행 중 owner를 제거하거나 cancel_event를 설정하면 commit하지 않고 rollback한다. valid 사례는 commit하며 child/root를 실제 FOR UPDATE owner/running SQL로 검증했다.

따라서 두 실제 routing 경로와 region publication transaction의 guard 누락을 수정한 것으로 확인하여 FIXED로 판정한다. Fake context의 rollback을 확인했으며 실제 PG의 이전 row 내용 보존을 본인 실측했다고 주장하지 않는다.

## 유지된 정상 동작 확인

- actual shadow_swap_mv의 parent/child 소유권 전후 검사, lost-parent와 cancel-during rollback.
- active serving release는 긴 통계 조회 뒤 owner를 잠그고 insert 후 cancel_event 재확인으로 같은 transaction을 rollback한다.
- concurrent MV의 긴 build 중 소유 행 lock을 미루고 commit 직전 owner/cancel을 검사한다.
- 원천 적재/MV/radius/release는 각각 transaction이며 전체 batch를 하나의 atomic transaction으로 만들지 않는 경계는 ADR-068과 일치한다.
- SQLite에서 production reconcile UPDATE의 now()만 CURRENT_TIMESTAMP로 치환한 CAS 검증: 관측한 owner 또는 lease가 바뀌면 running 행을 회수하지 않는다.
- 실제 _reconcile_rows 발행 SQL을 받는 Fake SQL engine의 201 terminal + 2 active 행: LIMIT100/keyset/활성·terminal 교대, 첫 probe 실제 5초 timeout 뒤 cursor 진행, terminal 두 페이지 중복 없음.
- UNKNOWN 조회 장애 보류, cancel poll 일시 read 오류 복구, owner에 연결된 worker progress/heartbeat/done 및 child 감시, retry policy 회귀.
- fixed pyproject.toml dependency와 ADR common SHA는 ab21cc3으로 일치한다.

## 본인 수행 결과와 negative control

fixed Geo에서:
```bash
python -m pytest -q tests/unit/test_dagster_reconciler.py tests/unit/test_dagster_recovery.py tests/unit/test_postload_mv.py tests/unit/test_batch_dag.py tests/unit/test_infra_repo_sql.py kor-travel-geo-dagster/tests/test_load_job_bridge.py kor-travel-geo-dagster/tests/test_recovery_policy.py kor-travel-geo-dagster/tests/test_mv_execute.py
```

- **111 passed, 1 warning in 2.98s**. 경고는 Dagster owners BetaWarning이다.
- 본인 /tmp 추가 test_closure.py test_independent.py test_geo_extra.py 전체 **19 passed in 29.60s** 중 Geo 사례 12개, common 사례 7개다. common PASS를 Geo gate로 합산하지 않았다.
- same concurrent/swap closure 시험에서 source만 이전 immutable ce82b07로 바꾼 별도 process는 **2 failed in 1.01s**. guard 없이 radius commit 후 cache clear에 도달하여 fail 단언이 실제 발생했다. 이 예상 실패는 제품 PASS가 아니며 시험의 판별력 evidence다.

## 증거 원문

- /tmp/recovery-postfix-independent/geo-test.log — SHA256 45cbd7cc7566d7d57ed8abf5c7241a33ebe3e301b4162cb089af00948f93b048
- /tmp/recovery-postfix-independent/postfix-tests.log — SHA256 8f5a68d85e685a81ec830ccb26f48fe29f9be946845ca5f827ba4f16c77f4f29
- /tmp/recovery-postfix-independent/test_closure.py — SHA256 15d75e90edac5528ced8fed38d41b899e2f743f6303b78aa85efe94b51cff696
- /tmp/recovery-postfix-independent/test_independent.py — SHA256 257b7f7051ddec33b8eb6e18a186d5627d364413959b609d2f7b303307c20933
- /tmp/recovery-postfix-independent/test_geo_extra.py — SHA256 0a729bc957341127b29d1fbcb4c0b892d7dfaa3b251898f12c0250bae29a4415
- /tmp/recovery-postfix-independent/old-geo-negative-control.log — 동일 closure의 구후보 실패 원문.
- /tmp/recovery-postfix-independent/run_negative.py — fixed source 교체 negative control 실행 script.

common의 독립 P1도 새 common candidate에서 FIXED로 확인했다. 이 PASS는 기능·복구 코드 범위 판정이며 미실행 PG/UI/운영·전체 gate를 통과로 표시하지 않는다.
