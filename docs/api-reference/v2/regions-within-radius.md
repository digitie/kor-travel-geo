# v2 Regions Within Radius

## 요약

`POST /v2/regions/within-radius`는 POI 좌표를 기준으로 반경 `n km` 안에 포함되는 행정구역을 반환한다. `krtourmap` ADR-045의 POI 주변 행정구역 판별 흐름에 맞춰, 하나의 점이 속한 행정구역뿐 아니라 반경 원과 겹치는 인접 시군구·읍면동도 함께 확인하는 용도다.

외부 인터페이스 좌표 순서는 항상 `(lon, lat)`이며, 입력 좌표계는 EPSG:4326이다. 내부 SQL은 입력 점을 한 번만 EPSG:5179로 변환한 뒤 PostGIS 공간 인덱스를 탈 수 있게 행정구역 원본 geometry를 그대로 `ST_DWithin`에 사용한다.

## 입력

| 필드 | 타입 | 기본값 | 설명 |
|------|------|--------|------|
| `lon` | number | 없음 | POI 경도. 한국 범위 `123..132` |
| `lat` | number | 없음 | POI 위도. 한국 범위 `32..39` |
| `radius_km` | number | `3.0` | 검색 반경 km. 최대 `500` |
| `levels` | array | `["sigungu", "emd"]` | 조회할 행정구역 레벨. `sido`, `sigungu`, `emd` 중 하나 이상 |

`levels`는 입력 순서를 유지하되 중복은 제거한다. 빈 배열은 허용하지 않는다.

## 출력

```json
{
  "center": { "lon": 126.978, "lat": 37.5665 },
  "radius_km": 3.0,
  "sido": [],
  "sigungu": [
    { "code": "11110", "name": "종로구", "relation": "contains" },
    { "code": "11140", "name": "중구", "relation": "overlaps" }
  ],
  "emd": [
    { "code": "11110119", "name": "세종로", "relation": "contains" }
  ]
}
```

응답은 요청하지 않은 레벨도 빈 배열로 둔다. 프론트엔드와 후속 batch 로직이 고정된 key를 안전하게 읽게 하기 위해서다.

## `relation`

| 값 | 의미 |
|----|------|
| `contains` | 행정구역 polygon이 POI 중심점을 포함한다. PostGIS에서는 `ST_Covers(region.geom, point)`로 판정한다. |
| `overlaps` | POI 중심점은 포함하지 않지만 반경 원 안에 행정구역 geometry가 들어온다. |

이 필드는 “POI가 속한 행정구역”과 “반경 때문에 함께 고려해야 할 인접 행정구역”을 분리하기 위한 표시다. 같은 레벨에서 `contains`가 0개일 수 있다. 예를 들어 좌표가 행정구역 polygon 외곽 오차나 자료 경계 밖에 있으면 `overlaps`만 반환될 수 있다.

## Python API

```python
async with AsyncAddressClient() as client:
    response = await client.regions_within_radius(
        lon=126.978,
        lat=37.5665,
        radius_km=3.0,
        levels=("sigungu", "emd"),
    )
```

`AsyncAddressClient.regions_within_radius()`는 REST DTO와 같은 `RegionsWithinRadiusResponse`를 반환한다.

## 예시

```bash
curl -X POST "http://localhost:9001/v2/regions/within-radius" \
  -H "Content-Type: application/json" \
  -d '{"lon":126.978,"lat":37.5665,"radius_km":3,"levels":["sigungu","emd"]}'
```

## 검증 기준

- SQL은 `tl_scco_ctprvn`, `tl_scco_sig`, `tl_scco_emd`를 사용한다.
- 입력점은 한 번만 `ST_Transform(ST_SetSRID(ST_MakePoint(:lon, :lat), 4326), 5179)`로 변환한다.
- 행정구역 geometry에는 `ST_Transform`을 걸지 않는다. 그래야 기존 geometry index를 사용할 수 있다.
- 거리 필터는 meter 단위 `radius_km * 1000`으로 적용한다.
