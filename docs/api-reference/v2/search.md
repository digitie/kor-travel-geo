# v2 Search

## 요약

`POST /v2/search`는 주소, 도로명, 행정구역, 장소 키워드를 같은 candidate schema로 반환한다.

## 입력

| 필드 | 타입 | 기본값 | 설명 |
|------|------|--------|------|
| `query` | string | 필수 | 검색어 |
| `type` | `address`, `place`, `district`, `road`, `category` | `address` | 검색 유형 |
| `category_group_code` | string | 없음 | category 검색 후보 코드 |
| `page` | integer | `1` | 페이지 |
| `size` | integer | `10` | 페이지 크기 |
| `sig_cd` | string | 없음 | 시도/시군구 hint |
| `bjd_cd` | string | 없음 | 법정동 hint |
| `bbox` | object | 없음 | `min_lon`, `min_lat`, `max_lon`, `max_lat`로 표현하는 EPSG:4326 비교 범위. 1차 구현은 입력과 응답 schema를 보존하고, 엄격한 공간 필터는 후속으로 확장한다. |

## 출력

- `status`
- `total`
- `candidates[]`: `match_kind`, `address`, `place`, `point`, `point_precision`, `distance_m`, `region`, `source`

`distance_m`은 향후 nearby/category 검색에서 기준점이 있을 때 first-class 필드로 사용한다. 현재 local road/address 검색은 거리 기준점이 없으므로 보통 `null`이다. `confidence`는 search score이며 geocode/reverse의 confidence와 같은 척도로 비교하지 않는다.

## 예시

```bash
curl -X POST "http://localhost:8000/v2/search" \
  -H "Content-Type: application/json" \
  -d '{"query":"테헤란로","type":"road","sig_cd":"11680","size":20}'
```

```python
async with AsyncAddressClient() as client:
    response = await client.search_v2(
        query="테헤란로",
        type="road",
        sig_cd="11680",
        bbox={"min_lon": 127.0, "min_lat": 37.45, "max_lon": 127.08, "max_lat": 37.55},
    )
```

## 구현 메모

`type="category"`는 현재 local place 검색으로 흡수된다. `category_group_code`는 Kakao 스타일을 참고한 분류 hint이지만 Kakao API를 직접 호출하지 않는다.
