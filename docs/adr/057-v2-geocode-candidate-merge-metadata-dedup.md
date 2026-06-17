# ADR-057: v2 geocode producer는 기존 tuple schema 안에서 후보를 병합하고 metadata 기반으로 dedup한다

- 상태: accepted
- 날짜: 2026-06-16
- 결정자: codex
- 관련: T-170, T-105, T-169, ADR-038, ADR-054, ADR-056

## 컨텍스트

v2 wire schema는 처음부터 `candidates: tuple[CandidateV2, ...]`였지만, geocode producer는 v1 `GeocodeResponse` 하나를 `CandidateV2` 하나로만 투영했다. T-170은 public schema를 바꾸지 않고 producer의 1건 collapse를 풀어 다점 후보를 방출해야 했다. 동시에 아직 `CandidateV2.candidate_id`나 `point_type` 같은 안정 first-class 식별자는 없으므로 중복 제거 규칙을 별도로 정해야 했다.

## 결정

1. `GeocodeV2Response.candidates` wire field는 그대로 둔다. 새 top-level field나 schema version bump는 만들지 않는다.
2. v2 변환 계층(`core/v2.py`)에 후보 dedup helper와 geocode 응답 병합 helper를 둔다.
3. dedup은 metadata와 구조화 필드의 안정 키를 우선한다. 우선순위는 국가지점번호(`national_point_number`), 건물관리번호(`bd_mgt_sn`), 도로명코드(`rncode_full`), 행정구역 코드(`bjd_cd`/`sig_cd`), POI 이름/좌표, fallback metadata 순서다.
4. 후보 순서는 producer가 낸 순서를 유지한다. v1 exact/local primary 후보는 보조 후보보다 앞에 두고, 같은 건물로 dedup되면 primary를 보존한다.
5. `limit`은 dedup 이후 적용한다. 중복 후보가 먼저 들어와도 뒤의 고유 후보가 limit 밖으로 밀리지 않게 한다.
6. `AsyncAddressClient.geocode()`는 local v1 geocode가 `OK`이고 입력이 정규화된 exact 주소와 다를 때만 보조 road geometry 후보를 병합한다. external fallback, 국가지점번호, 순수 지번 입력, `limit=1`은 보조 병합을 생략한다.
7. v1 REST/내부 `GeocodeResponse` 계약은 변경하지 않는다.

## 근거

- public schema는 이미 후보 tuple을 표현하므로 OpenAPI/typegen 변경 없이 producer 품질만 개선할 수 있다.
- dedup을 변환 계층에 두면 reverse/search/geocode 보조 후보가 같은 규칙을 공유한다.
- metadata 기반 dedup은 임시방편이지만 현재 schema에서 새 public field 없이 가능한 가장 보수적인 방법이다.
- exact 주소 요청마다 보조 검색을 강제하면 hot path 비용이 늘어난다. 정규화 결과와 입력이 다른 부분/모호 입력에서만 보조 후보를 붙이는 편이 T-170 목적과 현 성능 제약을 함께 만족한다.

## 결과(긍정)

- v2 geocode가 같은 응답 안에서 primary 주소 후보와 보조 도로 후보를 함께 반환할 수 있다.
- 중복 row가 limit을 잡아먹는 회귀를 막는다.
- v1 호환 응답과 기존 DTO wire shape는 유지된다.

## 결과(부정)

- 후보 식별자는 아직 metadata 추론에 의존한다. 서로 다른 후보가 같은 `bd_mgt_sn`을 공유하면 하나로 접힌다.
- 상세주소/다중 출입구처럼 point type 구분이 필요한 후보는 별도 public field가 생기기 전까지 metadata 계약을 더 명확히 해야 한다.

## 후속

- (open) T-105 재audit에서 `candidate_id`, `point_type`, pagination/error model을 함께 재검토한다.
- (open) 상세주소 typed candidate와 all-points 후보를 구현할 때 dedup 키를 first-class field 중심으로 승격할지 결정한다.
