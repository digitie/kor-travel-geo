# T-057: 행정구역 hint(`sig_cd` / `bjd_cd`) 기반 검색 가속

## 상태

- 상태: 1차 구현 및 실측 완료
- 대상 브랜치: `codex/t057-region-hint-search`
- 사용자 RFC: 2026-05-27 — "법정동 혹은 시군구코드를 제시하고 검색을 시키면 좀 더 빠른지 확인. 가능하다면 신규 API 및 함수에도 반영할 것. 예: 주소상 서울특별시 안에 있는게 확실한 좌표인 경우."

## 결론

명시 행정구역 hint를 `AsyncAddressClient`와 `/v1/address/*` query parameter에 추가했고, raw SQL 저장소와 T-047 benchmark harness에도 같은 바인드 파라미터를 연결했다. 응답 구조는 vworld 호환성을 유지하며 자체 필드는 추가하지 않았다.

실측 결론은 다음과 같다.

- DB client benchmark에서는 Q3 fuzzy `sig_cd` hint가 p95 기준 c1/c16/c64 모두 개선됐다. 다만 같은 입력에서 행정구역 문자열까지 제거한 wide no-hint 경로가 c64에서 더 낮게 나와, region hint만으로 Q3 병목을 끝냈다고 보기는 어렵다.
- REST smoke에서는 Q1 도로명, Q3 fuzzy, Q4 search, Q6 reverse radius가 hint로 개선됐다. Q2 지번 c64와 Q5 reverse nearest는 악화 구간이 있어 엔드포인트별 반복 측정이 필요하다.
- `mv_geocode_target`에는 물리 `sig_cd` 컬럼이 없으므로 이번 PR은 신규 index 없이 `bjd_cd` prefix filter로 `sig_cd`를 적용했다. 즉 `sig_cd=11680`은 `bjd_cd LIKE '11680%'`, `sig_cd=11`은 `bjd_cd LIKE '11%'`로 동작한다.
- Q3 fuzzy의 다음 후보는 `mv_geocode_text_search` 같은 slim text-search MV 또는 trgm 전용 후보 테이블이다. 이 후속은 T-061로 분리한다.

## 공개 입력 표면

### 라이브러리

`AsyncAddressClient`의 기존 함수에 선택 parameter를 추가했다.

```python
await client.geocode(query="테헤란로 152", sig_cd="11680")
await client.geocode(query="청운동 1-1", bjd_cd="1111010100")
await client.search(query="선릉로", sig_cd="11680")
await client.reverse(127.0, 37.5, sig_cd="11")
```

`sig_cd`는 2자리 시도 prefix 또는 5자리 시군구 코드를 받는다. `bjd_cd`는 8자리 법정동 prefix 또는 10자리 법정동 코드를 받는다.

### REST API

기존 vworld 호환 v1 엔드포인트에 선택 query parameter를 추가했다.

| 엔드포인트 | 추가 parameter | 의미 |
|----------|----------------|------|
| `/v1/address/geocode` | `sig_cd`, `bjd_cd` | geocode exact/fuzzy 후보를 행정구역으로 제한 |
| `/v1/address/search` | `sig_cd`, `bjd_cd` | 통합 search 후보를 행정구역으로 제한 |
| `/v1/address/reverse` | `sig_cd`, `bjd_cd` | reverse 후보를 행정구역으로 제한 |

hint가 들어온 geocode 요청에서 로컬 DB가 `NOT_FOUND`이면 외부 fallback은 호출하지 않는다. 현재 vworld/juso fallback은 이 hint를 보존하지 못하므로, hint 밖의 결과를 돌려주는 편보다 명시 `NOT_FOUND`가 더 안전하다.

응답 DTO와 OpenAPI 응답 schema는 바꾸지 않았다. schema 변경은 query parameter 추가뿐이며, `openapi.json`과 `kor-travel-geo-ui/types/api.gen.ts`를 재생성했다.

## 구현 세부

`RegionHint` DTO를 추가해 SQL 바인드 파라미터를 공통화했다.

| 입력 | SQL bind | SQL 적용 |
|------|----------|----------|
| `sig_cd=11` | `sig_cd_prefix='11%'` | `bjd_cd LIKE '11%'` |
| `sig_cd=11680` | `sig_cd_filter='11680'` | `bjd_cd LIKE '11680%'` |
| `bjd_cd=11110101` | `bjd_cd_prefix='11110101%'` | `bjd_cd LIKE '11110101%'` |
| `bjd_cd=1111010100` | `bjd_cd_filter='1111010100'` | `bjd_cd = '1111010100'` |

적용 범위:

- `core.geocoder.geocode()`가 도로명 exact, 지번 exact, fuzzy road repository 호출에 hint를 전달한다.
- `core.searcher.search()`와 `core.reverse_geocoder.reverse_geocode()`도 repository로 hint를 전달한다.
- `GeocodeRepository`, `SearchRepository`, `ReverseRepository` SQL에 같은 region filter를 추가했다.
- T-047 SQL benchmark corpus에 `road_exact_sig`, `parcel_exact_bjd`, `fuzzy_geocode_wide`, `fuzzy_geocode_sig`, `search_sig`, `reverse_nearest_sig`, `reverse_radius_sig`를 추가했다.
- REST benchmark harness는 hint case를 `/v1/address/*?sig_cd=...` 또는 `?bjd_cd=...` 요청으로 변환한다.

이번 PR에서는 parser가 주소 문자열의 시도/시군구명을 코드로 자동 변환하는 로직과 `bbox` hint는 넣지 않았다. 명시 hint의 효과를 먼저 분리 측정하기 위해서다.

## DB 실측

실행 조건:

| 항목 | 값 |
|------|----|
| artifact | `artifacts/perf/t057-region-hint-standard-20260528` |
| corpus SHA-256 | `e38bff5631a3b68fe6094e9124641a22f24770b9a040e8a70d067f1ea651d61f` |
| case count | 900 |
| measurement | 8,100 |
| iterations/warmup | `2 / 1` |
| concurrency | `1, 16, 64` |
| row count | `mv_geocode_target=6,416,637`, `tl_sppn_makarea=24,204` |
| error | 0 |

핵심 p95 비교:

| query | c1 기준 | c1 hint | c16 기준 | c16 hint | c64 기준 | c64 hint | 해석 |
|-------|------------:|--------:|-------------:|---------:|-------------:|---------:|------|
| Q1 도로명 exact | 6.80ms | 4.48ms | 28.37ms | 30.68ms | 342.91ms | 341.12ms | 단일 실행은 개선, c64는 차이 작음 |
| Q2 지번 exact | 4.33ms | 4.00ms | 24.27ms | 23.38ms | 231.11ms | 226.78ms | 소폭 개선 |
| Q3 fuzzy | 12.90ms | 11.69ms | 40.77ms | 35.91ms | 307.45ms | 267.99ms | hint로 개선 |
| Q4 search | 5.76ms | 5.64ms | 31.81ms | 32.08ms | 290.39ms | 279.96ms | c64 소폭 개선, c16은 거의 동일 |
| Q5 reverse nearest | 4.43ms | 4.36ms | 23.78ms | 24.35ms | 223.70ms | 207.41ms | c64 개선, c16 소폭 악화 |
| Q6 reverse radius | 4.15ms | 4.36ms | 22.84ms | 22.71ms | 229.89ms | 175.27ms | c64 개선 폭 큼 |

Q3은 추가로 `fuzzy_geocode_wide`를 함께 측정했다. 이는 주소 문자열에서 `si`/`sgg`를 제거하고 hint도 주지 않은 경로다.

| query | c1 p95 | c16 p95 | c64 p95 |
|-------|-------:|--------:|--------:|
| `fuzzy_geocode` | 12.90ms | 40.77ms | 307.45ms |
| `fuzzy_geocode_sig` | 11.69ms | 35.91ms | 267.99ms |
| `fuzzy_geocode_wide` | 11.20ms | 38.89ms | 253.23ms |

`sig_cd` hint는 기존 parsed-region fuzzy보다 낫지만, wide 경로가 c64에서 더 낮아지는 구간이 있어 planner와 trgm 후보 폭을 더 직접 줄이는 구조가 필요하다.

## REST smoke 실측

실행 조건:

| 항목 | 값 |
|------|----|
| artifact | `artifacts/perf/t057-region-hint-rest-smoke-20260528` |
| corpus | `artifacts/perf/t057-region-hint-standard-20260528/corpus.json` |
| corpus SHA-256 | `e38bff5631a3b68fe6094e9124641a22f24770b9a040e8a70d067f1ea651d61f` |
| REST case count | 320 |
| measurement | 1,920 |
| iterations/warmup | `1 / 1` |
| concurrency | `1, 16, 64` |
| error | 0 |

대표 c64 p95:

| API group | 기준 | hint | 해석 |
|-----------|---------:|-----:|------|
| Q1 geocode road | 805.64ms | 484.20ms | 개선 |
| Q2 geocode parcel | 540.93ms | 658.92ms | 악화 |
| Q3 geocode fuzzy | 651.62ms | 520.43ms | 개선 |
| Q4 search | 898.96ms | 661.50ms | 개선 |
| Q5 reverse nearest | 514.86ms | 687.42ms | 악화 |
| Q6 reverse radius | 652.94ms | 541.62ms | 개선 |

REST run은 각 SQL group 최대 20건의 smoke/e2e 검증이다. 운영 profile 확정용 반복 측정은 아니며, API 표면이 실제로 hint를 받아 정상 응답하는지와 대략적인 방향성을 확인하는 용도다.

## 판단

유지:

- `sig_cd`/`bjd_cd` 명시 hint 입력 표면.
- SQL 바인드 파라미터 공통화.
- hint가 있는 local `NOT_FOUND`에서 외부 fallback을 우회하는 정책.
- benchmark harness의 hint case와 REST 변환.

도입하지 않음:

- 신규 `sig_cd` index. 현재 MV에는 별도 `sig_cd`가 없고, `bjd_cd` prefix만으로도 낮은 위험의 1차 효과를 확인했다.
- 시도별 partial index. 관리 비용과 refresh/swap 비용을 정당화할 만큼 큰 개선은 아직 없다.
- parser 자동 hint 생성. 명시 입력 효과부터 분리해야 하므로 보류한다.
- `bbox` hint. reverse spatial 후보 축소에는 유용하지만 좌표계와 API 의미가 별도 설계가 필요하므로 T-052/T-061 이후로 미룬다.

## 후속

- T-061: Q3 fuzzy 전용 `mv_geocode_text_search` 또는 slim 후보 테이블을 설계하고, `rn_nrm`/`buld_nm_nrm` trgm 후보 폭을 직접 줄인다.
- T-052: v2 API를 만들 때 `RegionHint`를 v2 request model에도 정식 포함하고, provider별 hint 지원 여부를 문서화한다.
- T-053: `/admin/performance`에서 hint vs no-hint benchmark artifact를 비교할 수 있게 한다.
- T-027 최종 클린 적재 전에는 이번 SQL 변경이 full-load/MV refresh 계약을 건드리지 않았음을 다시 확인한다.
