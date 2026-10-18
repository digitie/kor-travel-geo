# ADR-068: 공통 Dagster 복구 정책과 운영 UI를 geo에서 채택한다

상태: accepted · 날짜: 2026-10-05

## 배경

Dagster 조회 장애를 실행 부재로 해석하면 lease가 만료된 정상 실행을 회수하고,
늦은 worker가 완료 상태를 덮어쓰면 앱과 orchestrator의 상태가 다시 갈라진다.
과거 실패 전체를 매 순회 적재하는 복구와 화면은 이력 증가에 따라 메모리를 소비한다.

## 결정

- mainlib의 순수 복구 판단은 Dagster를 import하지 않는다. 조회 실패는 UNKNOWN이며
  확인 가능한 terminal/부재만 회수한다. worker 쓰기는 run 소유권과 running 상태를
  확인하고, reconciler는 관측한 run ID·lease가 그대로인 행만 원자적으로 변경한다.
- 복구는 활성/과거 이력을 교대로 100행씩 keyset 조회하며 순회 DB/RPC 대기를 제한한다.
  실패한 순회는 다음 tick에서 재확인한다. DB statement/lock 대기를 무제한 해제하지 않는다.
- 별도 Dagster 패키지는 common의 RecoveryPolicy·활성 실행 확인·인프라 재시도 sensor를
  사용한다. 실행당 step 동시성은 1이다. 읽기 전용 backup_verify만 worker 장애 재시도
  1회를 허용하며 op/provider 실패는 제외한다. 비멱등 복원·적재는 자동 재시도하지 않는다.
- 긴 네 작업은 24시간, 나머지는 6시간의 명시적 run 예산을 가진다. instance의 run
  monitoring 및 JOB_TAG별 queue limit=1 설정은 별도 운영 전제이며 step 동시성과 다르다.
- 로그인·메뉴·Dagster 목록/상세 틀은 common UI를 사용한다. geo 고유 실패 승인·백업
  artifact·단계 event 상세는 geo에 남긴다. 공통 목록은 50행씩 표시한다.
- API는 최근 실행과 별도로 오래된 활성 실행을 조회·중복 제거한다. 활성 1,000건 및
  GraphQL 4MiB 상한에 도달하면 부분 결과를 정상으로 표시하지 않는다. UI는 오류 시
  마지막 성공 snapshot과 오류 안내를 유지하고 요청을 취소할 수 있다.

## 결과와 이관

React 19 peer와 Node 22 환경으로 소비자 검증을 수행한다. Python common은 확정된
73e3ff8b9398e533806d2d1a8435292570169de3로 고정한다. UI/tokens는 vendor tarball과
lock integrity로 고정하며 출처는 vendor/PROVENANCE.md에 기록한다.
공통 가이드: [Dagster 채택 가이드](https://github.com/digitie/kor-travel-common/blob/main/docs/runbooks/dagster-adoption.md).
상한은 적재·렌더링 구조의 개선이며 실제 RSS 감소율은 측정하지 않았다.

게시 단계는 자식과 batch root의 running/owner 행을 같은 SQL transaction에서 잠그고,
실제 MV 교체·release 활성화 직전과 commit 전에 중지 여부를 확인한다. 중지되면 해당
게시 transaction을 rollback한다. 이전에 commit된 원천 적재와 MV transaction은 보존하며,
전체 batch를 하나의 transaction으로 묶지는 않는다. 별도 serving 테이블인 region_radius_parts의 TRUNCATE/INSERT도 완료 후 commit 직전에 같은 owner 검증을 거치며, 취소 시 이전 테이블 내용이 유지된다. MV 유지보수·릴리스 SQL에는 30분 상한을 둔다(2026-10-18 개정: 6h — 아래 "개정" 절).
관측 조회의 전체 응답 예산은 기본 10초(최대 20초)이고 실행/취소의 기존 제한과 분리한다.
Dagster 1.13.24에서 tick 조회가 전체 이력을 순위 계산하지 않도록 모든 tick status를
명시해 최신 3건 제한 조회를 사용한다. 응답 크기와 전체 읽기 시간 제한을 함께 적용한다.

### 개정 (2026-10-18, G-01) — 유지보수 SQL 상한 30분 → 6시간

위 "MV 유지보수·릴리스 SQL에는 30분 상한"을 **`MAINTENANCE_STATEMENT_TIMEOUT = '6h'`**(문장당,
`src/kortravelgeo/infra/engine.py`)로 바꾼다. odroid(A55·열 제약) `mv_refresh`(`job_fb535a34…`,
2026-10-15)가 호스트 경합(load ≈20) 중 링크 해소 UPDATE에서 정확히 30분에 `QueryCanceled`로
실패했다 — Dagster 유지보수 엔진의 세션 값은 `0`인데 리프의 `SET LOCAL '30min'`이 그것을 낮췄다.
조용한 odroid 실측(2026-10-17, 읽기 전용·rollback): 그 UPDATE 120 s, `mv_geocode_target` 정의 쿼리
510 s — 평시엔 30분 안이지만 경합 시 한 문장이 넘을 수 있다. 6시간은 `mv_refresh` run 상한(ADR-070
D4, 21600 s)과 같아 `mv_refresh`에서는 한 문장이 run 예산 전체를 쓸 수 있되(`full_load_batch` 24 h 안의
같은 리프에는 문장당 6 h가 그대로 걸린다), run 감시(daemon)가 꺼져 있거나 worker가 죽어도 PostgreSQL이 **6 h 뒤에는**
취소한다(무한 상한 0은 고르지 않았다). 한계: 상한은 문장 단위라 daemon OFF 동안 run 전체 시간은 묶이지 않고,
`client_connection_check_interval`이 없어 worker가 죽은 뒤 고아 backend도 최대 6 h 돈다; `region_radius_parts`
TRUNCATE는 `lock_timeout` 없이 AccessExclusive를 commit까지 쥔다(기존 문제, 최악이 30분→6 h로 커짐) — 둘 다 후속
과제(tasks.md G-01 후속). → 2026-10-18 후속 a(#590): ACCESS EXCLUSIVE **획득 대기**만 2 s × 재시도(최대 1 h)로 묶었다; 보유 시간은 그대로. 21600 s 자체도 D4 실측 전 잠정값이다. D4가 run 상한을 올리면
`kor-travel-geo-dagster/tests/test_definitions.py`의 상한 검사가 빨개져 이 값을 다시 보게 한다.
데이터 지문의 savepoint 안 `10min`(ADR-069 D5)은 이 개정에서 바꾸지 않는다 — odroid 조용한 실측 240 s로 여유가
2.5배뿐이라 경합 시 NULL `data_token`(소비자 "판정 불가")이 될 수 있다. 올릴지는 네 활성화 경로가 공유하는 값이라
소유자 결정으로 남긴다(tasks.md G-01 후속). → **2026-10-18 소유자 결정: 30 min으로 올린다**(ADR-069 D5 개정,
`DATA_FINGERPRINT_STATEMENT_TIMEOUT`).
