# v1 Reverse

## 요약

`GET /v1/address/reverse`는 vworld `getAddress`와 같은 HTTP envelope를 유지하는 좌표 → 주소 API다.

## 입력

| 필드 | 타입 | 기본값 | 설명 |
|------|------|--------|------|
| `x` | float | 필수 | 경도 |
| `y` | float | 필수 | 위도 |
| `crs` | string | `EPSG:4326` | 입력 좌표계 |
| `type` | `both`, `road`, `parcel` | `both` | 반환 주소 유형. 입력은 대소문자를 구분하지 않는다. |
| `zipcode` | boolean | `true` | 우편번호 보강 여부 |
| `simple` | boolean | `false` | 간소 응답 여부 |
| `radius_m` | integer | 설정 기본값 | 검색 반경 |
| `sig_cd` | string | 없음 | 시도/시군구 hint |
| `bjd_cd` | string | 없음 | 법정동 hint |

## 출력

HTTP 응답 최상위는 항상 `response`다.

- `response.service.name`: `address`
- `response.service.operation`: `getAddress`
- `response.status`: `OK`, `NOT_FOUND`, `ERROR`
- `response.input.type`: `BOTH`, `ROAD`, `PARCEL`
- `response.result[]`: 가까운 도로명/지번 주소 후보

각 `result[]` 항목은 `text`, `type`, `structure`, `point`, `zipcode`, `distance_m`, `source`를 포함할 수 있다. HTTP 응답의 주소 유형은 `ROAD` 또는 `PARCEL` 대문자로 직렬화한다. `simple=true`이면 vworld와 같이 `response.input`을 생략하고 `result[]` 항목의 `type`도 생략한다.

입력 `type`은 대소문자를 구분하지 않아 응답값(`BOTH`/`ROAD`/`PARCEL`)을 그대로 다시 보낼 수 있다.

에러는 `response.status="ERROR"`와 `response.error.level/code/text`로 반환한다. 요청 검증 에러의 대표 code는 `PARAM_REQUIRED`, `INVALID_TYPE`, `INVALID_RANGE`다. 국가지점번호 reverse code는 vworld 원응답을 오염시키지 않도록 `response.x_extension.national_point_number`에 둔다. 표기 의무지역 보조 문맥도 `response.x_extension.sppn_makarea`에만 둔다.

## 예시

```bash
curl -G "http://localhost:12501/v1/address/reverse" \
  --data-urlencode "x=127.036" \
  --data-urlencode "y=37.501" \
  --data-urlencode "type=both"
```
