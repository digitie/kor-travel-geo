# T-170 v2 producer 1:N candidate-list 전환

## 요약

`/v2/geocode`와 `AsyncAddressClient.geocode()`의 wire schema는 그대로 두고, producer가 여러 후보를 낼 수 있게 했다. `GeocodeV2Response.candidates`는 기존 tuple field를 유지한다.

## 변경

- `core/v2.py`에 후보 dedup helper와 geocode 응답 병합 helper를 추가했다.
- `geocode_v2_from_search()`와 `geocode_v2_from_geometry_lookups()`는 중복 제거 후 `limit`을 적용한다. 중복 row가 먼저 들어와도 뒤의 고유 후보가 limit 밖으로 밀리지 않는다.
- `reverse_v2_from_v1()`과 `search_v2_from_v1()`도 같은 dedup helper를 사용한다.
- `AsyncAddressClient.geocode()`는 local v1 geocode가 `OK`이고 입력이 정규화된 exact 주소와 다를 때, 보조 road geometry 후보를 조회해 primary 후보 뒤에 병합한다.
- v1 REST/내부 `GeocodeResponse` 경로는 바꾸지 않는다.

## dedup 규칙

명시적인 `candidate_id`는 아직 public schema에 없으므로 metadata와 구조화 필드를 안정 키로 사용한다.

1. 국가지점번호: `metadata.national_point_number`
2. 건물: `metadata.bd_mgt_sn`
3. 도로: `rncode_full` + 주소 title + 좌표
4. 행정구역: `bjd_cd` 또는 `sig_cd`
5. POI: 이름 + category code + 좌표
6. 나머지: `match_kind`, `source`, 좌표, metadata repr

먼저 나온 후보를 유지한다. 따라서 v1 exact/local primary 후보가 보조 후보와 같은 건물로 판단되면 primary가 남고 보조 중복 후보는 제거된다.

## 범위

이번 작업은 producer collapse 해제와 dedup에 한정한다. `CandidateV2.candidate_id`, `point_type`, 상세주소 typed candidate, all-points MV 같은 더 큰 계약 변경은 T-105 재audit 또는 후속 작업에서 다룬다.

## 검증

- `tests/unit/test_v2_api.py::test_async_client_geocode_merges_local_primary_and_supplemental_candidates`
- `tests/unit/test_v2_api.py::test_geocode_v2_geometry_candidates_dedupe_before_limit`
- `python -m pytest tests/unit/test_v2_api.py -q`
- `python -m ruff check src/kortravelgeo/core/v2.py src/kortravelgeo/client.py tests/unit/test_v2_api.py`
- `python -m mypy --strict src/kortravelgeo/core/v2.py src/kortravelgeo/client.py`
