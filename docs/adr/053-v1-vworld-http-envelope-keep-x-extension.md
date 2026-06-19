# ADR-053: REST v1 geocode/reverse는 VWorld HTTP envelope를 맞추고 자체 확장은 유지한다

- 상태: accepted
- 날짜: 2026-06-15
- 결정자: 사용자 요청, codex
- 관련: T-106, ADR-003, ADR-038, ADR-039, ADR-050

## 컨텍스트

T-106은 v1 geocoding/reverse를 vworld와 100% 호환되는지 재점검하라는 작업이다. 착수 전 ADR-050은 먼저 호환 수준을 확정하라고 했다. 기존 ADR-038은 v1을 "현재 DTO 그대로 동결 + vworld-style key + `x_extension`"으로 설명했지만, VWorld Geocoder API 2.0의 HTTP JSON 응답은 최상위 `response` 아래에 `service`, `status`, `input`, `refined`, `result`, `error`를 둔다. 또한 `input.type`/`result[].type`은 `ROAD`, `PARCEL`, `BOTH` 대문자다.

한편 이 프로젝트는 이미 local/PostGIS 보강 정보(`bd_mgt_sn`, `rncode_full`, `bjd_cd`, `zip_no`, 국가지점번호 표기 의무지역 문맥)를 `x_extension`에 격리해 노출해 왔다. 이를 제거하면 ADR-003과 기존 REST v1 소비자 계약을 깨고, v2 변환에도 불필요한 손실이 생긴다.

## 결정

1. T-106의 v1 호환 수준은 **HTTP geocode/reverse envelope와 공개 key/대소문자 호환**으로 정의한다. byte-for-byte VWorld 원응답 동일성은 목표로 하지 않는다.
2. `/v1/address/geocode` 정상 응답은 `{"response": ...}`로 감싼다. `response.service.name`은 `address`, `response.service.version`은 `2.0`, `response.service.operation`은 `getCoord`로 직렬화한다.
3. `/v1/address/reverse` 정상 응답도 `{"response": ...}`로 감싼다. `response.service.name`은 `address`, `response.service.version`은 `2.0`, `response.service.operation`은 `getAddress`로 직렬화한다.
4. HTTP 직렬화의 주소 유형은 대문자로 낸다. geocode `response.input.type`은 `ROAD`/`PARCEL`, reverse `response.input.type`은 `BOTH`/`ROAD`/`PARCEL`, reverse `result[].type`은 `ROAD`/`PARCEL`이다. 내부 Python DTO 값은 기존 로직과 v2 변환을 위해 소문자 값을 유지한다.
5. geocode `simple=true`는 `response.input`과 `response.refined`를 생략한다. `refine=false`는 `response.refined`만 생략한다.
6. reverse에 `simple` 쿼리 파라미터를 추가한다. `simple=true`는 `response.input`을 생략하고 `result[]` 항목의 `type`도 생략한다.
7. v1 geocode/reverse의 요청 검증·도메인 에러는 `response.service.{name,version,operation}`, `response.status="ERROR"`, VWorld식 `response.error.level/code/text`로 반환한다. 대표 매핑은 `PARAM_REQUIRED`, `INVALID_TYPE`, `INVALID_RANGE`, `OVER_REQUEST_LIMIT`, `SYSTEM_ERROR`다.
8. `NOT_FOUND`는 에러가 아니라 정상 HTTP 응답 body의 `response.status="NOT_FOUND"`로 유지한다. HTTP status는 성공 응답 200을 유지한다.
9. `x_extension`은 제거하지 않는다. 자체 확장은 오직 `response.x_extension` 아래에 둔다. VWorld 원응답과 byte-for-byte 동일한 strict mode가 필요하면 별도 opt-in API 또는 v2 전용 변환으로 다시 ADR을 세운다.

## 근거

- VWorld 소비자가 기대하는 가장 큰 wire 차이는 최상위 `response` envelope, `service.operation`, `type` 대소문자, `error` 객체다. 이 부분은 HTTP v1 라우터에서만 바로잡을 수 있다.
- Python 공개 API는 ADR-039에 따라 v2 후보 목록 계약이므로, 내부 v1 DTO를 byte-for-byte VWorld 모델로 바꾸면 오히려 v2 변환과 로컬 보강 정보가 불안정해진다.
- `x_extension` 제거는 국가지점번호, 우편번호 출처, 로컬 key traceability를 잃게 하므로 "vworld 필드 오염 금지" 원칙과 충돌하지 않는 범위에서 유지하는 편이 낫다.

## 결과

- `/v1/address/geocode`와 `/v1/address/reverse`의 OpenAPI 응답 schema는 `VWorldGeocodeEnvelope`, `VWorldReverseEnvelope`로 바뀐다.
- `openapi.json`, `kor-travel-geo-ui/types/api.gen.ts`, `kor-travel-geo-ui/lib/schemas.gen.ts`를 함께 갱신한다.
- v1 HTTP 회귀 테스트는 DB 없이 dependency override로 envelope, 대문자 type, `simple`, 요청 검증 error object를 고정한다.

## 남은 위험

- 기존 v1 HTTP 소비자가 최상위 `service`/`status`를 직접 읽었다면 breaking change다. 다만 T-106의 목표와 VWorld 문서 기준으로는 `response.*`가 올바른 wire shape다.
- OpenAPI schema는 Pydantic serializer의 serialization schema를 따른다. query parameter는 여전히 소문자 입력(`road`, `parcel`, `both`)이고, 응답 field는 대문자 enum이다.
- VWorld의 실제 HTTP status code와 세부 error text는 API key/요청 조건에 따라 달라질 수 있다. 본 ADR은 공식 문서의 JSON 구조와 이 저장소의 운영 status code 보존 정책을 기준으로 한다.
