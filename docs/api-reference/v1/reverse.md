# v1 Reverse

## 요약

`GET /v1/address/reverse`는 vworld 호환에 가까운 좌표 → 주소 API다.

## 입력

| 필드 | 타입 | 기본값 | 설명 |
|------|------|--------|------|
| `x` | float | 필수 | 경도 |
| `y` | float | 필수 | 위도 |
| `crs` | string | `EPSG:4326` | 입력 좌표계 |
| `type` | `both`, `road`, `parcel` | `both` | 반환 주소 유형 |
| `zipcode` | boolean | `true` | 우편번호 보강 여부 |
| `radius_m` | integer | 설정 기본값 | 검색 반경 |
| `sig_cd` | string | 없음 | 시도/시군구 hint |
| `bjd_cd` | string | 없음 | 법정동 hint |

## 출력

`result[]`는 가까운 도로명/지번 주소 후보를 담는다. 각 항목은 `text`, `type`, `point`, `distance_m`, `zipcode`, `source`를 포함할 수 있다.

## 예시

```bash
curl -G "http://localhost:8888/v1/address/reverse" \
  --data-urlencode "x=127.036" \
  --data-urlencode "y=37.501" \
  --data-urlencode "type=both"
```
