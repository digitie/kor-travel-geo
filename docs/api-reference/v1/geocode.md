# v1 Geocode

## 요약

`GET /v1/address/geocode`는 vworld 호환 응답을 유지하는 주소 → 좌표 API다.

## 입력

| 필드 | 타입 | 기본값 | 설명 |
|------|------|--------|------|
| `address` | string | 필수 | 검색할 도로명 또는 지번 주소 |
| `type` | `road` 또는 `parcel` | `road` | 주소 유형 |
| `crs` | string | `EPSG:4326` | 출력 좌표계 |
| `refine` | boolean | `true` | 정규화 주소 반환 여부 |
| `simple` | boolean | `false` | 간소 응답 후보 |
| `fallback` | `off`, `local_only`, `api` | `local_only` | 외부 API fallback 사용 여부 |
| `sig_cd` | string | 없음 | 2자리 시도 또는 5자리 시군구 hint |
| `bjd_cd` | string | 없음 | 8자리 또는 10자리 법정동 hint |

## 출력

- `status`: `OK`, `NOT_FOUND`, `ERROR`
- `refined`: vworld 호환 정제 주소 구조
- `result.point`: `x=lon`, `y=lat`
- `x_extension.source`: `local`, `api_vworld`, `api_juso`, `cache`
- `x_extension.bd_mgt_sn`, `rncode_full`, `bjd_cd`, `zip_no`: 로컬 또는 provider에서 얻은 보강 필드

## 예시

```bash
curl -G "http://localhost:8888/v1/address/geocode" \
  --data-urlencode "address=서울특별시 강남구 테헤란로 152" \
  --data-urlencode "type=road" \
  --data-urlencode "fallback=api"
```

Python 라이브러리 공개 표면은 후보 목록 응답만 제공한다. vworld 호환 v1 응답이 필요하면 REST `/v1/address/geocode`를 직접 호출한다.

## Provider fallback

`fallback=api`이면 local DB가 `NOT_FOUND`일 때만 외부 provider를 호출한다. 호출 순서는 기존 ADR-019와 같이 `vworld` → `juso`다. region hint가 들어간 요청은 외부 fallback을 호출하지 않는다.
