# T-217 — T-214 SQL benchmark 독립 재실행 (Agent B)

작성일: 2026-06-15
담당: Claude (Agent B)

## 목적

PR #185가 추가한 T-213 r3 기준 DB 접속 정보(`KTG_PG_DSN` template, `localhost:5432` / `kor_travel_geo_t213_20260615_r3`)가 실제로 활용 가능한지 확인하고, T-214 SQL benchmark를 **독립적으로 재실행**해 SQL c64 tail이 무회귀인지 재확인한다. (T-214는 Codex #180, REST 수용은 T-216 #187에서 별도 처리됨.)

## 기준 입력

| 항목 | 값 |
|------|----|
| DB | `kor_travel_geo_t213_20260615_r3` (container `kor-travel-geo-postgres`, `localhost:5432`) |
| PostgreSQL/PostGIS | 16.9 / 3.5.2 |
| 식별성 검증 | `mv_geocode_target`=`mv_geocode_text_search`=6,419,795, `tl_sppn_makarea`=24,204, active serving release `54e17e80-312e-46da-a58f-d8b10be37c85` — #185/T-214/T-215/T-216 baseline과 일치 |
| harness | `scripts/benchmark_query_performance.py` (read-only; corpus는 DB에서 생성) |
| 설정 | cases-per-group=100, iterations=3, warmup=1, concurrency 1/4/16/64, pool size=20 / max_overflow=64, statement_timeout 5,000ms (T-214 동일) |
| artifact | `/tmp/t217-sql/` (WSL 미러; repo 비커밋) — run id `t217-r1` |

## 결과

- query group 8종(Q1_ROAD_EXACT, Q2_PARCEL_EXACT, Q3_FUZZY_GEOCODE, Q4_SEARCH, Q5_REVERSE_NEAREST, Q6_REVERSE_RADIUS, Q7_ZIPCODE, Q8_NO_RESULT) × concurrency 1/4/16/64.
- **total error 0**.
- **worst c64 p95 = `Q4_SEARCH/search_fuzzy` 268.370ms**.

| run | worst c64 p95 (Q4_SEARCH/search_fuzzy) | errors |
|-----|----------------------------------------|-------:|
| T-214 (#180) | 245.895ms | 0 |
| T-215 (#183) | 308.617ms | 0 |
| **T-217 (이 실행)** | **268.370ms** | **0** |

worst tail은 세 실행 모두 동일 쿼리(`Q4_SEARCH/search_fuzzy`)이고 268ms는 T-214~T-215 band(246~309ms) 안에 들며 오류가 없다 → **SQL c64 tail 무회귀를 독립 확인**. 절대값 변동은 공유 DB 부하/실행 환경 noise 범위다.

## 범위

- **SQL**: 이 문서로 독립 재실행 완료.
- **REST**: T-216(#187)에서 동일 425-case 표본으로 재측정·수용(worst p95 `415.022ms` ≤ T-214 `534.031ms`)했으므로 재실행 생략.
- **MV refresh/swap, RustFS reconcile**: 기준 DB가 Codex 작업과 **공유**되는 baseline이라 MV swap 같은 write·RustFS(현재 `KTG_RUSTFS_ENABLED=false`) 의존 측정은 제외했다. 필요 시 전용 DB 복제 또는 Codex와 시간대 조율 후 T-126에서 수행한다.

## 결론

#185 접속 정보는 활용 가능하며(하네스가 TCP로 정상 접속, baseline 데이터 일치), T-214 SQL benchmark는 독립 재실행에서도 오류 0·c64 tail band 내로 재확인됐다.
