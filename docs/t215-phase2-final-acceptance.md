# T-215 phase ② 튜닝·최종 검증 평가

작성일: 2026-06-15
담당: Codex(Agent A)

## 기준 입력

T-215는 T-214와 같은 T-213 r3 전용 기준 데이터를 사용했다. 기본 개발 DB `kor_travel_geo`를 암묵적으로 쓰지 않는다.

| 항목 | 값 |
|------|----|
| PostgreSQL DB | `kor_travel_geo_t213_20260615_r3` |
| RustFS bucket/prefix | `kor-travel-geo` / `kor-travel-geo/t213/20260615-rerun3` |
| T-213 artifact | `F:\dev\geodata\t213-baseline\20260615-rerun3\` |
| T-214 artifact | `F:\dev\geodata\t214-benchmark\20260615-r3\` |
| T-215 artifact | `F:\dev\geodata\t215-acceptance\20260615-r1\` |
| source match set | `a0c2d514-a91d-44c4-bdb6-0bc4771ae61a` |
| serving release | `54e17e80-312e-46da-a58f-d8b10be37c85` |
| dataset snapshot | `1b354560-52bc-4ec6-8760-55fed63d9e98` |

실행은 WSL ext4 미러 `/home/digitie/ktg-codex-t215-test`에서 수행했다. 로컬 `.env`의 PostgreSQL 접속 정보가 실제 T-213 r3 DB 인증과 맞지 않아, 검증 중에만 임시 PostgreSQL role을 만들고 검증 후 삭제했다. 비밀번호는 artifact나 문서에 남기지 않았다.

## Preflight

`preflight.json`에서 다음을 모두 확인했다.

| 검사 | 결과 |
|------|------|
| current database | 일치 |
| active serving release | 일치 |
| active dataset snapshot | 일치 |
| active source match set | 일치 |
| 핵심 row count | 일치 |

핵심 row count는 T-213/T-214 기준과 같았다.

| relation | rows |
|----------|-----:|
| `tl_juso_text` | 6,419,795 |
| `tl_locsum_entrc` | 6,405,091 |
| `tl_navi_buld_centroid` | 10,687,317 |
| `tl_navi_entrc` | 12,830 |
| `tl_spbd_buld_polygon` | 10,687,732 |
| `tl_roadaddr_entrc` | 6,404,697 |
| `tl_sppn_makarea` | 24,204 |
| `mv_geocode_target` | 6,419,795 |
| `mv_geocode_text_search` | 6,419,795 |

## v1/v2 smoke

API 서버를 같은 기준 DB에 붙여 `F:\dev\geodata\t215-acceptance\20260615-r1\rest-smoke\`에 응답을 남겼다. `KTG_GEOIP_GATE_MODE=off`로 로컬 smoke만 확인했다.

입력 주소: `경기도 용인시 수지구 성복1로 35`

| 표면 | 결과 |
|------|------|
| `GET /v1/address/geocode` | HTTP 200, `OK` |
| `POST /v2/geocode` | HTTP 200, `OK`, 후보 1건 |
| `GET /v1/address/search` | HTTP 200, `OK`, 결과 3건 |
| `POST /v2/search` | HTTP 200, `OK`, 후보 3건 |
| `GET /v1/address/zipcode` | HTTP 200, `OK`, `16856` |
| `GET /v1/address/reverse` | HTTP 200, `OK`, 결과 10건 |
| `POST /v2/reverse` | HTTP 200, `OK`, 후보 10건 |

대표 좌표는 `127.07430262108355, 37.31347098160811`이고, reverse 첫 후보도 같은 도로명주소와 우편번호 `16856`을 반환했다.

## C1~C10 정합성

새 report id는 `consistency_87ce6c3f2d574cfca39976a5a8f74f3d`이고 `severity_max=ERROR`다. 이는 T-213 r3가 `force_promotion=true`로 운영 반영된 known data-quality 상태임을 다시 확인한 결과다.

| case | severity | count | 주요 metric |
|------|----------|------:|-------------|
| C1 | `WARN` | 33,897 | 텍스트에만 존재 |
| C2 | `ERROR` | 32,496 | `missing_text=31,915`, `missing_resolve_key=581` |
| C3 | `WARN` | 3,513,854 | 대표 출입구 미해소 |
| C4 | `ERROR` | 3,416 | `p95=3.824m`, `over_500m=16` |
| C5 | `WARN` | 202 | `p95=0.000001m` 미만, `over_10m=202` |
| C6 | `ERROR` | 803 | `outside_polygon=803` |
| C7 | `ERROR` | 6,815 | `outside_polygon=6,815` |
| C8 | `WARN` | 24,483 | 도로 key 결손/불일치 |
| C9 | `OK` | 0 | PNU 형식 위반 없음 |
| C10 | `WARN` | 7 | `distinct_months=2` |

C10 sample 기준 `tl_juso_text`는 `202605`, 나머지 core/optional serving relation은 `202604`다. 이 혼합은 T-213 r3에서 명시적으로 force promotion한 상태이며, 기준년월이 없는 자료는 `202604`로 갈음한다는 정책과 함께 해석해야 한다.

## C11~C17 run-validation

`run_consistency_validation()`을 source match set `a0c2d514-a91d-44c4-bdb6-0bc4771ae61a`에 대해 실행했다.

| 항목 | 결과 |
|------|------|
| runnable | 0 |
| skipped | 7 |
| failed | 0 |
| quarantined group | 0 |
| affected match set | 0 |

현재 T-213 r3 `serving_recommended` match set은 운영 full-load 6종만 포함한다. 따라서 `roadaddr_building_shape_bundle`, `detail_address_db_full`, `national_point_grid_*`, `civil_service_institution_map`, `address_db_full`, `building_db_full`, `navi_full.match_jibun`, `tl_juso_parcel_link` 같은 보강 검증 입력은 absent로 판정되어 C11~C17이 모두 `skipped`가 됐다.

이번 결과는 "현재 serving baseline에서 보강 source가 없을 때 run-validation이 실패 없이 skipped 처리된다"는 확인이다. C11~C17 optional source까지 포함한 운영 검증은 별도 match set을 구성해 다시 실행해야 하며, 이는 T-126으로 분리한다.

RustFS verifier 자격 증명은 이 세션에 노출되어 있지 않아 run-validation은 DB 상태 판정 경로로 실행했다. 원천 object 정합성은 T-214의 quick/deep reconcile 결과를 함께 acceptance 근거로 사용한다.

## 성능 재측정

T-214에서 c64 tail이 컸던 부분만 재측정했다.

| 범위 | artifact | 조건 | errors | worst p95 |
|------|----------|------|-------:|----------:|
| SQL c64 | `query-c64-rerun\` | pool `20/64`, iterations 2, warmup 1 | 0 | `Q4_SEARCH/search_fuzzy=308.617ms` |
| REST c64 sample | `rest-c64-rerun-pool20\` | REST case 425, pool `20/64`, iterations 2, warmup 1 | 0 | `Q3_FUZZY_GEOCODE/geocode_fuzzy_hint=3631.900ms` |

참고로 REST를 기본 pool `10/5`로 띄운 sample은 worst p95 `3709.033ms`였고, `--max-cases-per-sql` 없이 1,800 case로 넓힌 stress 실행은 Q4 fuzzy 일부가 `NOT_FOUND`로 잡혀 T-214와 직접 비교하지 않는다.

SQL tail은 T-214의 `245.895ms`보다 높지만 timeout/error는 없다. 반면 REST c64 tail은 T-214의 `534.031ms`보다 크게 악화됐다. 실행 환경 차이(Python 3.13 → 3.14, Docker bridge IP, 임시 role, 단일 uvicorn 프로세스)가 섞여 있으나, API 계층 pool/admission/worker 설정은 추가 튜닝 없이는 성능 acceptance로 닫지 않는다.

## 최종 판정

T-215는 최종 검증 평가 자체는 완료했다. 결론은 다음과 같다.

- **기준 데이터 식별성 통과**: DB/release/snapshot/source match set/row count가 T-213 r3와 일치한다.
- **기능 smoke 통과**: v1/v2 geocode/search/reverse/zipcode 대표 경로가 모두 HTTP 200/`OK`다.
- **정합성은 clean pass가 아니다**: C2/C4/C6/C7 `ERROR`와 C10 `WARN`은 known source-quality/혼합 기준월 상태로 남아 있다.
- **C11~C17은 skipped**: 현 serving match set이 보강 검증 원천을 포함하지 않아 optional validation full acceptance는 별도 작업이 필요하다.
- **REST c64 성능은 미수용**: SQL은 오류 없이 300ms대지만 REST sample p95가 3초대로 악화되어 pool/admission/실행환경 튜닝 후 재측정이 필요하다.
- **N150/Odroid 실측은 보류**: 실제 하드웨어가 준비되면 T-063 runbook으로 연결한다.

따라서 T-109 phase ②는 core serving 경로의 기능/식별성 검증까지는 닫고, optional C11~C17 운영 검증과 REST c64 성능 수용은 T-126 후속으로 남긴다.
