# 역지오코딩

`kraddr-geo`의 역지오코딩은 `core.reverse_geocoder.reverse_geocode()`와 `infra.reverse_repo.ReverseRepository`가 담당한다. 라이브러리 진입점은 `AsyncAddressClient.reverse_geocode(lon, lat, ...)`이며 REST 엔드포인트는 `GET /v1/address/reverse`다.

> 이전(v1) SpatiaLite 기반 `SpatialiteAddressStore.get_address()`는 `v1` 브랜치에 보존되어 있다. master는 PostgreSQL + PostGIS / `AsyncAddressClient` 기준만 다룬다(ADR-001, ADR-002).

## 입력

```python
class ReverseInput(BaseModel):
    point:    Point             # (x=lon, y=lat) — 외부 인터페이스는 (lon, lat) 고정
    crs:      str = "EPSG:4326"
    type:     Literal["both","road","parcel"] = "both"
    zipcode:  bool = True
    radius_m: int  = Field(default=200, ge=1, le=2000)
```

`model_validator(mode="after")`가 EPSG:4326일 때 한국 경위도 범위(`123<x<132, 32<y<39`)를 강제. 벗어나면 `InvalidCoordinateError("point out of Korea bounds")` — hint에 "좌표가 (lon,lat) 순서인지 확인".

## 흐름

1. 입력 좌표를 EPSG:5179 WKT로 변환은 repo 내부에서 `ST_Transform`으로 처리. core는 좌표값만 넘긴다.
2. `repo.nearest_entrance(point_5179_wkt=..., limit=1)` — `tl_spbd_entrc`의 GiST 인덱스로 최근접 출입구 1개.
3. `near["dist_m"] <= inp.radius_m`이면 **출입구 hit** → 도로명/지번 둘 다 만들 수 있음.
   - 우편번호: `near["zip_no"]`가 있으면 `(zip_no, "building_bsi_zon_no")`. 없고 `inp.zipcode`면 `repo.zip_at(...)`로 4단계 fallback.
   - `inp.type ∈ {"both","road"}`이면 도로명 `ReverseItem` 생성 (`level5=road_nm`, `detail=본번-부번`, `x_extension.matched="entrance"`).
   - `inp.type ∈ {"both","parcel"}`이면 지번 `ReverseItem` 생성.
4. 출입구 hit 실패 → **동 폴리곤 fallback**: `repo.emd_at(...)`로 `tl_scco_emd` polygon 안의 행을 찾아 지번만 구성.
5. 모두 실패하면 `ReverseResponse(status="NOT_FOUND")`.

## 우편번호 lookup 4단계 우선순위

`repo.zip_at(point_5179_wkt=...)`는 `ZipSource` enum과 함께 `(zip_no, zip_source)`를 반환한다:

1. **`building_bsi_zon_no`** — 출입구의 건물 BSI에 우편번호가 들어있는 경우 (가장 신뢰도 높음)
2. **`bulk_delivery`** — `postal_bulk_delivery`에서 `bd_mgt_sn` 매핑이 있는 경우
3. **`kodis_bas_within`** — `tl_kodis_bas` polygon 안에 점이 들어가는 경우
4. **`kodis_bas_centroid`** — `kodis_bas_within`이 실패하면 centroid 거리로 fallback

`postal_pobox`는 사서함 도메인이므로 좌표 기반 역지오코딩 lookup에는 사용하지 않는다(주소 입력 기반 zipcode lookup에서만 사용).

## API 예시

```python
import asyncio
from kraddr.geo import AsyncAddressClient

async def main():
    async with AsyncAddressClient() as client:
        r = await client.reverse_geocode(127.028601, 37.500344, type="both", zipcode=True)
        for item in r.result:
            print(item.type, item.text, item.zipcode, item.x_extension.get("zip_source"))

asyncio.run(main())
```

REST:

```
GET /v1/address/reverse?point=127.028601,37.500344&crs=EPSG:4326&type=both&zipcode=true&radius_m=200
```

응답은 vworld 호환 구조 (`service`, `status`, `input`, `result: list[ReverseItem]`). 각 item에 `x_extension`(`bd_mgt_sn`, `distance_m`, `matched ∈ {"entrance","polygon"}`, `zip_source`)가 들어간다.

## 디버깅 UI

`kraddr-geo-ui`의 `/debug/reverse` 페이지에서 VWorld/MapLibre 지도를 클릭하면 `(lon, lat)` 입력값이 갱신된다. 운영자가 조회 버튼을 누르면 `/v1/address/reverse` 응답을 JSON 뷰어로 확인한다. EXPLAIN으로 인덱스 사용을 확인하려면 `/debug/explain`에서 raw SQL을 붙여 실행한다. 지도 wrapper에서 공통 VWorld/MapLibre 문제가 발견되면 `digitie/maplibre-vworld-js`도 수정 대상에 포함하고, reverse geocode 입력/결과 표시처럼 이 프로젝트 특화 동작은 `kraddr-geo-ui`에 둔다.

## 알려진 함정

- **좌표 순서**: 외부 인터페이스는 모두 `(lon, lat)`. `(lat, lon)`을 받으면 한국 범위 검증에서 즉시 실패하며, 범위에 우연히 들어맞으면 잘못된 위치를 반환한다(SKILL.md §4-5).
- **`radius_m`이 너무 크면** 노이즈가 늘어 인접 건물이 hit될 수 있다. 기본 200m 권장.
- **`type="road"` 단독 사용**: 출입구 hit 실패 시 동 폴리곤 fallback은 지번만 만들므로 빈 결과로 보일 수 있다.
- **외부 API 폴백 미적용**: 현재 사양에서 `/v1/address/reverse`는 로컬 결과만 반환한다. vworld의 역지오코딩 폴백이 필요해지면 새 ADR로 결정.
