# Geo 최종 evidence 후보 독립 기능·복구 리뷰 원문

- execution ID: /root/review_recovery_final / recovery-evidence-independent
- 전문 영역: Dagster 상태 회수·worker 소유권·취소·serving publication
- 검증 시작: 2026-10-04T23:02:31Z
- 검증 종료: 2026-10-04T23:07:47Z
- 작성일: 2026-10-05 KST
- repository: /mnt/f/dev/kor-travel-geo-codex-dagster-common
- manifest base: 3f4ddc2dac3f31634a23ef0e9592f419e29e7d14
- immutable source candidate: **4c59efe3a778fb160b7d0a4fde2ca08967bf1531**
- fixed common dependency: **73e3ff8b9398e533806d2d1a8435292570169de3**
- 직전 검토 source: 596b7d177517f3b53cb811e36720d9af9bba582b
- 검토 범위 판정: **PASS**
- 열린 actionable finding: 0건. 기존 본인 B-P2-01: **FIXED 유지**.
- review 분류 의견: **FULL**, review closure artifact 예외 **부적용**.

## 고정·독립성·검토 경계

Linux git archive로 /tmp/recovery-evidence-independent/geo에 새 immutable 사본을 만들었다. fixed common도 별도 archive했다. 기존 dirty checkout과 후속 문서 HEAD를 source로 섞지 않았다. 이전 보고서를 수정하거나 다른 현행 reviewer 원문/부모 journal 판정을 열람하지 않았다.

기존 /home/digitie/dev/kor-travel-geo-codex-dagster-common-test/.venv/bin/python을 설치 변경 없이 실행만 재사용하고 본인 source만 PYTHONPATH에 지정했다. product/원본/설치/외부 서비스·DB는 수정하지 않았다. 본인 /tmp SQLite/Fake SQL 및 보고서만 작성했다.

본인 실제 PostgreSQL/PostGIS lock/MV rollback, RustFS, 외부 API, UI/live, 운영 Dagster daemon·worker 장애 주입, 설치·전체 저장소 gate·CI는 **NOT_RUN**이다. 부모 제공 PG/UI evidence를 본인 수행 결과로 주장하거나 합산하지 않는다.

## 전체 delta와 review 방식 판단

596b7d1→4c59efe 전체 diff는 다음 두 파일뿐이다:

1. kor-travel-geo-dagster/pyproject.toml: exact common dependency를73e3ff8b9398e533806d2d1a8435292570169de3로 변경한다.
2. docs/adr/068-common-dagster-recovery-and-ui.md: 위 dependency SHA를 같은 값으로 정정한다.

git diff --exit-code 596b7d1 4c59efe -- src kor-travel-geo-dagster/src tests kor-travel-geo-dagster/tests는 exit0였다. 따라서 UI/publication/state recovery 제품 코드가 이전 독립 후보와 같다는 parent 설명은 source diff로 본인이 확인했다.

base→최종의 기능·복구 변경은 이전 본인 리뷰에서 UNKNOWN 조회 보류, observed owner/lease CAS, 100행 keyset 교대, worker owner 감시, cancel poll, 실제 MV/release/radius publication guard를 검토했다. 이번 새 고정 source와 새 common dependency로 관련111개 및 본인 publication/CAS/keyset 시험을 재실행했다. UI 부분은 이 reviewer의 판정 범위가 아니다.

delta 자체는 작지만 dependency pin은 build/config이며 ADR은 규범 정본이다. 결과 보존/disposition/index만 갱신하는 review closure artifact가 아니다. 동일 gate의 일반 면제 조건을 충족하지 않으므로 독립 의견은 FULL이다. 단순 link correction/light 또는 closure 예외로 축소하지 않았다.

## 공격한 시나리오와 closure 유지

- B-P2-01: guarded MV commit 직후 cancel_event를 설정해 concurrent/swap 각각 실제 refresh_mv 후속 radius 경로를 실행했다. radius TRUNCATE/INSERT transaction은 rollback하며 이미 commit된 MV는 보존하고 cache clear로 진행하지 않는다.
- 실제 refresh_region_radius_parts INSERT 중 owner를 제거하거나 cancel_event를 설정하면 commit 직전 guard가 거부해 rollback한다. valid owner는 commit하며 child/root를 같은 connection에서 FOR UPDATE running+owner 조건으로 검증한다.
- shadow_swap_mv parent/child guard의 valid/lost-parent/cancel-during, actual active release insert 후 취소 rollback, concurrent build 중 취소 rollback을 새 사본에서 유지했다.
- 긴 build/statistics 중 소유 행 잠금이 미뤄지고 해당 publication commit 직전에 검증하는 위치를 확인했다. 전체 batch를 하나의 atomic transaction으로 묶는다고 주장하지 않는다.
- SQLite의 production reconcile UPDATE(now만 CURRENT_TIMESTAMP로 치환)는 observed owner 또는 lease가 바뀌면 running 행을 terminal로 바꾸지 않는다.
- 실제 _reconcile_rows SQL을 받는 Fake SQL engine에서201 terminal+2 active 행으로 LIMIT100, tuple keyset, 활성/terminal 교대와 실제5초 first probe timeout 뒤 cursor 진행을 확인했다.
- UNKNOWN 조회 장애 보류, transient cancel read 복구, child heartbeat owner 상실→cancel_event, owner-bound progress/done, read-only backup verify retry1 예산을 새 common dependency와 함께 확인했다.
- 새 common의 late-child/legacy checkpoint 보강도 본인 별도 SQLite 시험에서 통과했고 이전 source ab21에서는 정상 child 복구 두 사례가 실패하여 dependency 변경의 실제 효과를 확인했다.

이 시험들은 actual production 함수·발행 SQL·transaction context를 검증하지만 실제 PostgreSQL locks/rollback 효과의 실측을 대체하지 않는다. 신규 actionable finding은 발견하지 않았다.

## 본인 실행 결과

fixed Geo 사본에서:
```bash
python -m pytest -q tests/unit/test_dagster_reconciler.py tests/unit/test_dagster_recovery.py tests/unit/test_postload_mv.py tests/unit/test_batch_dag.py tests/unit/test_infra_repo_sql.py kor-travel-geo-dagster/tests/test_load_job_bridge.py kor-travel-geo-dagster/tests/test_recovery_policy.py kor-travel-geo-dagster/tests/test_mv_execute.py
```

- **111 passed, 1 warning in 3.30s**. 경고는 Dagster owners BetaWarning이다.
- 본인 test_evidence.py test_closure.py test_independent.py test_geo_extra.py: **29 passed in 30.95s** 중 Geo12개/common17개.
- common 전용 latest attributes 추가3개는 Geo gate로 합산하지 않는다.
- common 전체69 PASS와 본인 negative control2FAIL도 Geo PASS 수로 합산하지 않는다.
- 최초29개 suite의1FAIL/28PASS는 common same-tick 재검증을 기대한 이전 시험과 새partial→next-tick 계약의 불일치였다. 본인 시험에 partial/no-request 및 next-tick provider 검증을 각각 추가 단언한 재실행29PASS를 사용했고 initial log도 보존했다.
- base→candidate git diff --check exit0. 이는 다른 전체 gate의 수행을 뜻하지 않는다.

추가 suite의 PYTHONPATH는 /tmp/recovery-evidence-independent/common/packages/py/kor-travel-common/src, 그 tests helper, Geo/src, Geo Dagster/src다. Python 설치는 위 기존 venv를 읽기 재사용했다.

## 원문 evidence와 SHA256

모든 파일은 /tmp/recovery-evidence-independent/ 아래에 있다.

- geo-test.log: 85fc09ae326f4262174eb752f3b7835eb81d99a1dba7969735031929087c052d
- independent-tests.log: 8a7589ae87039f59bc73efbd1fbe097c46640a494fc60f7d6f852571eaef67a4
- test_independent.py: fc73be56786f7e7bc7909b4c4f0c28216c00da8dcfb482f3904d077f741283ae
- test_closure.py: 15d75e90edac5528ced8fed38d41b899e2f743f6303b78aa85efe94b51cff696
- test_geo_extra.py: 0a729bc957341127b29d1fbcb4c0b892d7dfaa3b251898f12c0250bae29a4415

최종 기능·복구 코드 판정: **PASS**. 본인의 이전 P2는 FIXED를 유지한다. external PG/UI/운영 및 다른 전문 영역의 미실행 gate는 이 판정으로 닫지 않는다.
