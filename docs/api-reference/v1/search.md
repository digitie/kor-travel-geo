# v1 Search

## 요약

`GET /v1/address/search`는 도로명/지번/행정구역/장소 후보를 기존 search DTO로 반환한다.

## 입력

| 필드 | 타입 | 기본값 | 설명 |
|------|------|--------|------|
| `query` | string | 필수 | 검색어 |
| `type` | `address`, `place`, `district`, `road` | `address` | 검색 유형 |
| `page` | integer | `1` | 페이지 |
| `size` | integer | `10` | 페이지 크기 |
| `sig_cd` | string | 없음 | 시도/시군구 hint |
| `bjd_cd` | string | 없음 | 법정동 hint |

## 출력

`result[]`와 `total`을 반환한다. 신규 UI에서 provider별 후보 차이를 비교하려면 v2 search를 우선 사용한다.

## 예시

```bash
curl -G "http://localhost:9001/v1/address/search" \
  --data-urlencode "query=테헤란로" \
  --data-urlencode "type=road" \
  --data-urlencode "sig_cd=11680"
```
