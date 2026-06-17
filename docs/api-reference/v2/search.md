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
| `include_geometry` | boolean | `false` | 후보에 도형(`geometry`/`bbox`) 포함 여부. geocode/reverse와 동일한 opt-in(ADR-060 §5, ADR-059) |

`include_geometry`는 geocode/reverse와 대칭으로 받는다. **현재 채워지는 경우는 `type="district"` 후보**다 — `match_kind="region"`이고 해석된 행정구역 코드(시도 2자리, 시군구 5자리, 법정동 8/10자리)로 region polygon(`geometry.kind="region"`)을 받는다. **도로명/지번/장소 후보는 도형이 채워지지 않는다(REST 응답에서 `geometry` 필드 생략)**: `bd_mgt_sn`/`rncode_full`/`bjd_cd`/건물번호 같은 건물 도형 조회 key가 v1→v2 search 변환(`metadata={"score"}`만 보존)에서 떨어져 building polygon을 조회할 수 없기 때문이다. 이 key들을 v2 metadata/address까지 보존해 도로/주소 후보도 도형을 받게 하는 것은 후속 작업으로 남긴다. 페이지네이션은 collection 규약(`page`/`size`+`total`, ADR-060 §3)을 따른다.

## 출력

공통 header `{status, query_id, input}` 위에 결과를 둔다:

- `status`
- `query_id`
- `total`
- `candidates[]`: `match_kind`, `address`, `place`, `point`(`{lon, lat}`), `region`, `source`. 값이 없는 선택 필드(`point_precision`/`distance_m`/`geometry`/`bbox`)는 REST 응답에서 생략된다.

`distance_m`은 향후 nearby/category 검색에서 기준점이 있을 때 first-class 필드로 사용한다. 현재 local road/address 검색은 거리 기준점이 없으므로 보통 `null`이다. `confidence`는 search score이며 geocode/reverse의 confidence와 같은 척도로 비교하지 않는다.

`type="district"`는 `tl_scco_ctprvn`, `tl_scco_sig`, `tl_scco_emd`, `tl_scco_li` 행정구역 polygon을 검색한다. 후보의 `match_kind`는 `region`이며, `point`는 polygon 내부 대표점(`ST_PointOnSurface`)이다. `수지구`처럼 복합 시군구명의 마지막 `구`만 입력해도 `용인시 수지구` 후보가 우선 반환된다. `type="place"` 또는 `type="category"`에서 장소 후보가 생기면 후보의 `match_kind`는 `poi`다.

## 예시

```bash
curl -X POST "http://localhost:12501/v2/search" \
  -H "Content-Type: application/json" \
  -d '{"query":"테헤란로","type":"road","sig_cd":"11680","size":20}'
```

```python
async with AsyncAddressClient() as client:
    response = await client.search(
        query="테헤란로",
        type="road",
        sig_cd="11680",
        bbox={"min_lon": 127.0, "min_lat": 37.45, "max_lon": 127.08, "max_lat": 37.55},
    )
```

## 구현 메모

`type="category"`는 현재 local place 검색으로 흡수되며, 후보가 있으면 `match_kind="poi"`로 표현한다. `category_group_code`는 Kakao 스타일을 참고한 분류 hint이지만 Kakao API를 직접 호출하지 않는다. 내비게이션용DB_전체분의 `시군구용건물명`은 후속 T-065에서 검색 후보에 포함한다.
