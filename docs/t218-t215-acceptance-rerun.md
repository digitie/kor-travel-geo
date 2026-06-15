# T-218 — T-215 acceptance 독립 재실행 (Agent B)

작성일: 2026-06-15
담당: Claude (Agent B)

## 목적

PR #185가 추가한 T-213 r3 기준 DB 접속 정보를 활용해 T-215 phase ② 최종 검증 acceptance를 **독립적으로 재실행**하고 결과가 재현되는지 확인한다. (T-215는 Codex #183, C11~C17 optional full run-validation은 T-216 #187에서 수행됨.)

## 기준 입력

| 항목 | 값 |
|------|----|
| DB | `kor_travel_geo_t213_20260615_r3` (container `kor-travel-geo-postgres`, `localhost:5432`) |
| active serving release | `54e17e80-312e-46da-a58f-d8b10be37c85` |
| custom source match set | `0c7d7ee7-75bf-4a1e-ae0b-015485e73656` (core 6 + augment 8 category) |

## 1. Preflight (read-only) — T-213 r3와 일치 ✅

| relation | rows |
|----------|-----:|
| `mv_geocode_target` | 6,419,795 |
| `mv_geocode_text_search` | 6,419,795 |
| `tl_sppn_makarea` | 24,204 |

active serving release `54e17e80…` 일치. custom match set `0c7d7ee7…` 항목 = core 6(electronic_map/locsum/navi/roadaddr_entrance/roadname_hangul/zone_shape) + augment 8(address_db/building_db/civil_service_institution_map/detail_address_db/detail_dong_shape_bundle/national_point_grid_center/national_point_grid_shape/roadaddr_building_shape_bundle).

## 2. C1~C10 정합성 (`run_all_cases`, read-only) — T-215와 byte-identical ✅

`severity_max=ERROR` (known data-quality + 혼합 기준월). 각 case count가 T-215(#183)와 정확히 일치:

| case | severity | count | case | severity | count |
|------|----------|------:|------|----------|------:|
| C1 | WARN | 33,897 | C6 | ERROR | 803 |
| C2 | ERROR | 32,496 | C7 | ERROR | 6,815 |
| C3 | WARN | 3,513,854 | C8 | WARN | 24,483 |
| C4 | ERROR | 3,416 | C9 | OK | 0 |
| C5 | WARN | 202 | C10 | WARN | 7 |

## 3. v1/v2 smoke — 전부 200/`OK` ✅

입력 `경기도 용인시 수지구 성복1로 35` (reverse는 대표 좌표 `lon=127.07430262108355, lat=37.31347098160811`).

| 표면 | 결과 |
|------|------|
| `GET /v1/address/geocode` | 200 `OK` |
| `GET /v1/address/search` | 200 |
| `GET /v1/address/zipcode` | 200 `OK` |
| `GET /v1/address/reverse` | 200 — 첫 후보 도로명주소 `경기도 용인시 수지구 성복1로 35`(round-trip 일치) |
| `POST /v2/geocode` | 200, 후보 1건 |
| `POST /v2/search` | 200, 후보 10건 |
| `POST /v2/reverse` | 200, 후보 10건 |

API 서버는 r3 DB에 `KTG_PG_DSN` 오버라이드 + `KTG_GEOIP_GATE_MODE=off` 로컬 smoke로 붙였다.

## 4. C11~C17 run-validation — 구조 확인 ✅

custom match set `0c7d7ee7…`이 augment 8 category를 포함 → C11~C17 runnable 입력이 존재(= T-216 `runnable=7 / skipped=0 / failed=0`와 정합). 전체 run-validation 실행은 T-216(#187)에서 완료됐고, 공유 baseline DB 재트리거(쓰기 가능)를 피하기 위해 본 재실행에서는 match set 구성 구조로 재확인했다.

## 결론

#185 접속 정보로 T-215 acceptance(preflight·C1~C10·v1/v2 smoke)를 **독립 재실행해 T-215/T-216 결과를 그대로 재현**했다. C1~C10은 count까지 byte-identical, v1/v2 smoke 전부 200/`OK`(reverse round-trip 일치), C11~C17은 match set 구조로 runnable 확인. 성능(SQL c64)은 T-217에서 별도 재확인. C1~C10 ERROR는 known source-quality 상태로 acceptance 결론은 T-215와 동일하다.
