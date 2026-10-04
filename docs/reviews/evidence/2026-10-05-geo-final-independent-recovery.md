# Geo 독립 기능·복구 리뷰 원문

- 리뷰어: recovery reviewer (/root/review_recovery_final)
- 날짜: 2026-10-05
- 고정 repository: /mnt/f/dev/kor-travel-geo-codex-dagster-common
- base: 3f4ddc2dac3f31634a23ef0e9592f419e29e7d14
- candidate: ce82b079619b9db8b8ccbcf540f13e9ab78acc91
- 고정 common dependency: 3194a0b6c81d64a75dc937f177588a300944b2af
- Geo 코드 판정: **CONDITIONAL**
- 열린 Geo finding: P2 1건. 의존 common의 별도 P1 finding 때문에 두 저장소 조합에 대한 승인 판정은 BLOCK이다. 제품 코드 수정 없음.

## 독립성·실행 경계

Linux git archive로 본인 /tmp/recovery-final-independent/geo 고정 사본을 만들었다. AGENTS.md, SKILL.md, README, architecture, resume, ADR 인덱스와 ADR-068, 공용 runbook을 참조했다. 작업은 기존 Python 설치의 실행 재사용, 고정 source import, 본인 로컬 SQLite/Fake SQL 테스트와 보고서 작성뿐이다. 원본 checkout, 기존 설치, 외부 서비스/DB는 수정하지 않았다. 다른 현행 리뷰어 결과나 부모 journal의 판정은 보지 않았다.

부모가 제공한 실제 PostgreSQL UUID 임시 schema 15 PASS와 MV rollback 및 Chromium/Firefox live 결과는 **본인 수행 결과가 아니다**. 이번 리뷰에서 PostgreSQL, PostGIS, RustFS, 외부 API, UI/live, 운영 Dagster daemon/worker 장애 주입, 전체 회귀·CI는 **NOT_RUN**이다.

## B-P2-01 — 취소 뒤 반경 검색용 serving 테이블을 guard 없이 commit한다

- 위치: src/kortravelgeo/loaders/postload.py:88, :92. swap에도 동일 호출이 :63에 있다.
- 실제 변경 SQL: src/kortravelgeo/infra/sql.py:1281 TRUNCATE TABLE region_radius_parts, :1328 INSERT.
- 실제 serving 소비: src/kortravelgeo/infra/geometry_repo.py:318, :335, :349.
- 상태: OPEN
- 영향: guarded MV transaction이 commit된 직후 작업이 cancelled/회수되거나 cancel_event가 설정되어도 worker가 반경 검색의 live relation을 별도 transaction으로 다시 게시한다. 다음 run_mv_refresh의 취소 검사에서 release 활성화는 막히지만 그 전에 지역 serving 데이터 교체는 이미 commit된다. commit된 기존 MV의 보존 자체는 문서화된 정상 경계다. finding은 그 이후 새로 시작하는 unguarded serving write에 한정한다.

### 실제 재현

본인 test_findings.py::test_radius_publish_after_cancel에서 실제 refresh_mv 함수를 Fake SQL engine으로 호출했다.

1. child owner/running guard가 통과하도록 설정했다.
2. 첫 MV transaction 정상 commit 직후에 asyncio.Event cancel_event를 설정했다.
3. 실제 refresh_mv의 후속 코드를 그대로 진행했다.
4. 두 번째 region_radius_parts transaction에서 실제 SQL 문자열 TRUNCATE/INSERT를 실행하고 commit했다.
5. 이 transaction에는 FROM load_jobs / FOR UPDATE / owner 검사나 cancel 검사 호출이 전혀 없었다.
6. refresh_mv는 오류 없이 반환했다. cache clear만 Fake로 치환하여 외부 DB에 쓰지 않았다.

출력: PROVEN geo: cancellation after MV commit still commits live region_radius_parts replacement

이것은 Fake SQL의 실제 PostgreSQL 원자성 검증이 아니라, production 호출 경로·SQL 발행·transaction 경계에 대한 재현이다. 실제 PG에서 row count나 query 결과의 변화를 재현했다고 주장하지 않는다.

권고: 반경 serving relation을 교체하는 transaction에도 PublicationGuard를 전달하고 commit 직전에 ownership/cancellation을 검증한다. 긴 subdivision 중 소유 행 잠금을 유지할 필요는 없고 transaction의 취소 시 rollback 경계를 확보하면 된다. swap과 concurrent 두 호출 경로가 모두 적용되어야 한다.

## 확인한 정상 동작과 한계

- Dagster transport/URL 조회 실패는 lease 만료 여부와 무관하게 UNKNOWN이며 정상/terminal 부재로 해석하지 않는다.
- reconciler의 terminal 변경 SQL은 running/executor + observed run ID + observed lease의 IS NOT DISTINCT FROM predicate를 하나의 UPDATE에 넣는다.
- 본인 SQLite 시험은 production SQL에서 now()만 SQLite CURRENT_TIMESTAMP로 치환했다. stale owner 또는 stale lease인 UPDATE는 행을 변경하지 않고, 일치할 때만 failed로 바뀌었다. PostgreSQL lock 경쟁의 실측은 아니다.
- 실제 _reconcile_rows가 발행하는 keyset SQL에 LIMIT 100, ORDER BY created_at, job_id, tuple cursor를 확인하는 Fake SQL engine으로 201 terminal 행과 2 active 행을 돌렸다. 실제 첫 probe가 5초 timeout되는 사례에서도 cursor가 첫 행 뒤로 이동했고, active/terminal이 교대로 진행하며 terminal 두 페이지의 100개 ID가 겹치지 않았다.
- cancel poll의 일시 read 오류는 task 종료로 이어지지 않고 성공·후속 cancel을 확인한다.
- root/child executor는 소유 run과 running 상태에 붙은 heartbeat/progress/done으로 늦은 worker가 상태를 되살리지 못한다. child heartbeat의 확인된 소유권 상실은 공유 cancel_event를 설정한다.
- 실제 shadow_swap_mv의 첫 transaction에서 parent/child guard를 각각 전후로 호출하며, 소유권 상실과 중간 cancel_event에 대해 rollback한다. parent가 running/owner가 아니면 교체 SQL 전부터 차단된다.
- 실제 record_mv_refresh_release는 긴 통계 조회를 먼저 하고 guard를 얻은 뒤 active release를 넣는다. insert 중 cancel_event를 설정하면 commit 직전 guard가 예외를 내고 같은 transaction을 rollback한다.
- concurrent refresh도 긴 build 중에는 소유행을 잠그지 않고 commit 직전 guard로 취소를 검증한다. Fake SQL 시험에서 build 중 cancel을 주입하니 해당 transaction이 rollback했다.
- 위 publication 시험은 transaction context가 rollback되는지와 guard의 실제 호출 위치·SQL predicate를 확인했다. 실제 PostgreSQL MV rollback이나 concurrent REFRESH locking은 본인 범위에서 미실행이다.
- MV 교체·release 활성화는 별도 transaction이며 전체 batch 원천 적재를 하나의 atomic transaction으로 묶지 않는 경계는 ADR-068과 일치한다.

## 본인 실행 결과

PYTHONPATH는 fixed common/src + fixed Geo/src + fixed Geo Dagster/src, Python은 /home/digitie/dev/kor-travel-geo-codex-dagster-common-test/.venv/bin/python이다.

고정 Geo 사본에서 다음을 실행했다:
```bash
python -m pytest -q tests/unit/test_dagster_reconciler.py tests/unit/test_dagster_recovery.py tests/unit/test_postload_mv.py tests/unit/test_batch_dag.py tests/unit/test_infra_repo_sql.py kor-travel-geo-dagster/tests/test_load_job_bridge.py kor-travel-geo-dagster/tests/test_recovery_policy.py kor-travel-geo-dagster/tests/test_mv_execute.py
```

- 결과: **110 passed, 1 warning in 2.82s**. 경고는 Dagster SensorDefinition owners의 BetaWarning이다.
- 본인 test_independent.py 전체 **11 passed in 2.65s** 중 Geo 5개: swap valid/lost-parent/cancel-during, release statistics/guard/rollback, concurrent build 취소 rollback. common 6개는 Geo gate로 합산하지 않는다.
- 본인 test_geo_extra.py: **2 passed in 5.58s**. SQLite CAS와 실제 발행 SQL keyset·100행 교대·느린 첫 행 검증.
- test_findings.py의 **2 passed in 30.79s** 중 Geo 사례 1개는 결함 존재를 단언한 재현이며 정상 gate로 세지 않는다.
- mutation-geo: 별도 임시 source 사본에서 swap/release의 commit 직전 guard를 각각 제거하고 관련 본인 시험을 실행하니 **2 failed in 1.00s**, 둘 모두 DID NOT RAISE LoadJobLeaseLostError였다. 따라서 시험은 guard가 빠진 구현을 실제 판별했다. candidate 사본은 변경하지 않았다.

증거:
- /tmp/recovery-final-independent/geo-test.log SHA256 1851d46b7f99f40f1b377011f95c648f0fd9b96884c1001effb3e75ec6e3c31a
- /tmp/recovery-final-independent/test_independent.py SHA256 ca59fd4b79131c2a263b5d9552786accdc5b3b9278f366b46657c69fe831bbb5
- /tmp/recovery-final-independent/test_geo_extra.py SHA256 0a729bc957341127b29d1fbcb4c0b892d7dfaa3b251898f12c0250bae29a4415
- /tmp/recovery-final-independent/geo-extra-test.log SHA256 12e5835a999fd729244a646ea4a6b56904b79595cfd5c85413cdfec995a4990c
- /tmp/recovery-final-independent/test_findings.py SHA256 bfffabaed39dbb0787cd274f3340427b94dab98ab93ae1faffb116bac56d385f

B-P2-01의 수정 또는 근거 있는 disposition과 의존 common P1 closure가 후속 조건이다.
