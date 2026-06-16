# T-173 negative/악성/경계 입력 안전성 하니스

## 목적

`geocode`/`reverse`/국가지점번호(SPPN) 입력에서 악성·경계 입력이 DB query나 core 변환까지 흘러가 500 또는 process crash로 번지지 않게 고정한다. 이번 범위는 새 검색 알고리즘이 아니라 **예외가 구조화된 4xx로 끝나는 안전성 계약**이다.

## 구현

- `GeocodeInput.address`와 v2 `GeocodeV2Input`의 `query`/`road_address`/`jibun_address`/`keyword`는 ASCII control character를 거절한다. 특히 `%00`/NUL 같은 입력이 SQL parameter 경로까지 내려가지 않게 DTO 단계에서 막는다.
- `ReverseV2Input.lon`/`lat`은 `FiniteFloat`로 바꾸고, v1 `ReverseInput`과 같은 한국 lon/lat bounds(`123 < lon < 132`, `32 < lat < 39`)를 검증한다.
- `RequestValidationError`도 기존 `ValidationError`와 같은 좌표 bounds 판정 helper를 사용한다. 좌표 범위 오류는 v2에서 `E0102`, 일반 request validation은 기존처럼 `E0100`/HTTP 400을 유지한다.
- malformed SPPN 문자열은 `parse_national_point_number()`에서 `None`으로 끝나거나 일반 주소 parser 경로에서 `NOT_FOUND`로 끝나며, crash하지 않는 것을 core fake repo 테스트로 고정했다.

## 하니스

`tests/unit/test_t173_input_safety.py`가 DB 없이 다음 표면을 검증한다.

- v2 geocode: 빈 body, control character 포함 주소, SPPN처럼 보이는 control character 포함 문자열
- v2 reverse: 한국 bounds 밖 좌표, non-finite 좌표, radius 하한 밖 값
- v1 geocode/reverse: 필수 query 누락, control character 포함 주소, 한국 bounds 밖 좌표
- core SPPN: envelope 밖 grid, trailing text, digit overflow 형태의 malformed 문자열

모든 API case는 `400 <= status_code < 500`, 최상위 `response`, `status="ERROR"`를 요구한다. VWorld 호환 v1 경로는 `response.error.code`, v2 경로는 `response.errorCode`를 확인한다.

## 비범위

- T-219의 non-vworld validation envelope 재결정은 하지 않는다. 이번 변경은 좌표 bounds 오류를 `E0102`로 보존하는 데 한정한다.
- `search`/`regions/within-radius`의 별도 입력 정책은 바꾸지 않는다.
- T-140 golden corpus case 수는 늘리지 않는다. T-173은 live DB가 아니라 API/DTO/core 안전성 하니스로 닫는다.

## 검증

```bash
python -m pytest tests/unit/test_t173_input_safety.py tests/unit/test_api_responses.py tests/unit/test_v1_vworld_compat.py tests/unit/test_v2_api.py -q
python -m ruff check src/kortravelgeo/dto/common.py src/kortravelgeo/dto/geocode.py src/kortravelgeo/dto/reverse.py src/kortravelgeo/dto/v2.py src/kortravelgeo/api/responses.py tests/unit/test_t173_input_safety.py
python -m mypy src/kortravelgeo/dto/common.py src/kortravelgeo/dto/geocode.py src/kortravelgeo/dto/reverse.py src/kortravelgeo/dto/v2.py src/kortravelgeo/api/responses.py
python scripts/export_openapi.py --check
```
