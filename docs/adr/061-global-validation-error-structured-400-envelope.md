# ADR-061: 전역 RequestValidationError 핸들러는 전 경로 구조화 400 envelope로 통일한다

- 상태: accepted
- 날짜: 2026-06-17
- 결정자: 사용자(옵션 a 선택) + claude
- 관련: T-219 M4(#305), T-106(#189), T-173, ADR-038, ADR-053, ADR-060(§4)

## 컨텍스트

T-106이 추가한 전역 `RequestValidationError` 핸들러(`api/responses.py`)는 vworld 경로(`vworld_operation_for_path`
매칭)는 VWorld error object 400으로, **그 외 모든 경로**는 `{response:{status:"ERROR", errorCode, errorMessage, hint?}}`
400으로 변환한다(FastAPI 기본 422 `{detail}` 대체). T-219 M4 구현 중 두 가지를 확인했다.

1. **단순 "v2 422 복원"은 T-173을 회귀시킨다.** `tests/unit/test_t173_input_safety.py`는 v2 public 경로
   (`/v2/geocode`·`/v2/reverse`·`/v2/search`)가 잘못된 입력에 구조화 `{response:{errorCode}}`(좌표 범위 → `E0102`)를
   **의도적으로** 반환함을 단언한다. 즉 비-vworld 구조화 400은 T-106의 사고가 아니라 T-173이 의존하는 input-safety 기능이다.
2. **`hint=str(exc.errors())`가 raw repr을 노출한다.** pydantic error 리스트의 repr에는 사용자 입력값(`input`),
   내부 `url`/`ctx`가 포함돼 응답으로 새고 계약이 불안정했다.

## 결정

1. **(사용자 결정, 옵션 a) 전 경로 검증 에러를 구조화 400 `{response:{...}}`로 통일 유지한다** — 비-address 경로
   (admin/zipcode/pobox/`regions/within-radius`) 포함. 단일 에러 envelope가 SDK·UI 분기 비용을 최소화한다. wire 무회귀.
2. v2 public address 경로(geocode/reverse/search, `regions/within-radius`)의 구조화 400은 **의도된 input-safety(T-173)**로 명문화한다. ADR-062 이후 v2는 `{status:"ERROR", query_id, error:{code,message,hint?,field?}}` 형태의 `V2ErrorEnvelope`를 명세하고, 오해 소지 자동 `422`를 억제한다(v1 vworld의 M3와 동일 패턴).
3. `hint`는 raw repr 대신 `loc: msg` 기반 sanitized 요약으로 교체한다(`_summarize_validation_errors`). 입력값·내부
   url/ctx를 노출하지 않으며, `extra='forbid'`가 만드는 `extra_forbidden`의 loc leaf(= 사용자가 보낸 키 이름)는
   reflect하지 않고 "unexpected field"로 일반화한다. bogus 키 대량 주입에 의한 응답 증폭을 막도록 항목 dedup +
   개수·길이 상한을 둔다. envelope 형태(`{response:{errorCode,errorMessage,hint?}}`)는 **비-breaking으로 유지**한다.
4. ADR-060 §4의 **v2 전용 error envelope 재구조화**는 ADR-062/T-268에서 배포 전 breaking 묶음으로 완료됐다. 본 ADR의 "전 경로 구조화 400" 원칙은 그대로 유지하되, v2 public 경로는 더 이상 legacy `{response:{errorCode}}` envelope를 쓰지 않는다.
5. admin/zipcode/pobox와 같은 legacy non-vworld 경로의 런타임 400은 유지한다. T-219 후속에서 이들 경로의 OpenAPI도 `LegacyErrorEnvelope` 400으로 명세하고 자동 `422`를 억제해 런타임과 문서 계약을 맞춘다.

## 근거

- T-173 input-safety를 깨지 않으면서 단일 에러 계약을 유지하는 가장 단순한 선택이 옵션 (a)다(wire 회귀 0).
- `hint` 정직화는 입력 누출을 막고 계약을 안정화하면서도 envelope 형태를 바꾸지 않아 비-breaking이다.
- envelope 재구조화(§4)를 지금 하지 않는 것은 ADR-060이 정한 "breaking은 배포 직전 묶음" 원칙과 일치한다.

## 결과

- `responses.py`: `hint`를 `_summarize_validation_errors`로 교체(extra-key leaf 미reflect·dedup·개수/길이 상한).
- v2 geocode/reverse/search/`regions/within-radius`에 `V2ErrorEnvelope` 400 명세 + 자동 `422` 억제(`_install_openapi_customization` 확장). openapi/typegen 재생성.
- legacy non-vworld 경로는 `LegacyErrorEnvelope` 400 명세 + 자동 `422` 억제로 런타임 400과 OpenAPI를 맞춘다.
