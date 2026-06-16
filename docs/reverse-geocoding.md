# 역지오코딩

`kor-travel-geo`의 역지오코딩은 `core.reverse_geocoder.reverse_geocode()`와 `infra.reverse_repo.ReverseRepository`가 담당한다. 라이브러리 진입점은 후보 목록 응답을 반환하는 `AsyncAddressClient.reverse(lon, lat, ...)`이며 REST v1 엔드포인트는 `GET /v1/address/reverse`다.

> 이전(v1) SpatiaLite 기반 `SpatialiteAddressStore.get_address()`는 `v1` 브랜치에 보존되어 있다. `main`은 PostgreSQL + PostGIS / `AsyncAddressClient` 기준만 다룬다(ADR-001, ADR-002).

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

1. 입력 좌표를 EPSG:5179로 변환하는 일은 repo 내부에서 `ST_Transform`으로 처리. core는 좌표값(`Point`)과 `crs`만 넘긴다.
2. `repo.nearest(point, crs=..., address_type=..., radius_m=..., limit=...)` — serving MV `mv_geocode_target`의 `pt_5179` GiST KNN 인덱스로 작은 후보군을 먼저 조회한 뒤 `distance_m <= radius_m`로 반경을 적용한다(T-142). MV의 좌표는 텍스트 정본(`tl_juso_text`)에 위치정보요약DB 대표 출입구(`tl_locsum_entrc`, same-month일 때만 `tl_roadaddr_entrc`)와 centroid fallback(`tl_navi_buld_centroid`)을 합친 것이며, 각 행의 `pt_source`가 `entrance`/`centroid`를 구분한다.
3. 최근접 정렬은 `t.pt_5179 <-> p.geom` KNN을 먼저 쓰고, 동률은 `distance_m ASC` → `pt_source='entrance'` 우선 → `bd_mgt_sn` → `rncode_full` → `bjd_cd` 순으로 결정한다.
4. 후보가 `radius_m` 이내이면 **hit**다. `distance_m <= radius_m` 기준이므로 경계 거리(`distance_m == radius_m`)도 포함한다.
   - 우편번호: 행의 `zip_no`가 있고 `inp.zipcode`가 true이면 `zip_source="building_bsi_zon_no"`로 함께 반환한다.
   - `inp.type="road"`이면 도로명 `ReverseItem`만 만든다.
   - `inp.type="parcel"`이면 지번 `ReverseItem`만 만든다.
   - `inp.type="both"`이면 SQL base row `limit`을 먼저 적용한 뒤 각 row를 `road`, `parcel` 순서로 fan-out한다. 내부 `limit=5` 기준 최대 10개 주소 후보가 나올 수 있다.
5. 주소 후보가 없더라도 `repo.project_reverse_point_5179(...)` 결과가 국가지점번호 지원 envelope 안에 있으면 `ReverseResponse(status="OK")`다. v1은 빈 `result`와 `x_extension.national_point_number`를 반환하고, v2는 `match_kind="sppn"` 후보를 반환한다.
6. 주소 후보도 없고 국가지점번호 context도 없으면 `ReverseResponse(status="NOT_FOUND")`다. 한국 lon/lat bounds 밖 입력은 DTO 단계에서 구조화 오류로 거절한다.

## 우편번호 lookup

v1 reverse 응답의 우편번호는 nearest 후보 row의 `zip_no`를 그대로 사용하며,
`zip_source="building_bsi_zon_no"`로 표시한다. 별도 좌표 기반 우편번호 lookup은
`ZipRepository.lookup_zipcode_by_point()`가 담당한다.

좌표 기반 우편번호 lookup은 입력 좌표를 EPSG:5179로 한 번 변환한 뒤
`ST_Covers(tl_kodis_bas.geom, target.geom)`로 기초구역 polygon을 조회한다(T-142).
경계 위 좌표도 포함하며 `ZipSource`는 `kodis_bas_within`이다. 현재 구현에는
`kodis_bas_centroid` fallback이 연결되어 있지 않다.

`postal_pobox`는 사서함 도메인이므로 좌표 기반 역지오코딩 lookup에는 사용하지 않는다(주소 입력 기반 zipcode lookup에서만 사용).

## API 예시

```python
import asyncio
from kortravelgeo import AsyncAddressClient

async def main():
    async with AsyncAddressClient() as client:
        r = await client.reverse(127.028601, 37.500344, include_zipcode=True)
        for item in r.candidates:
            address = item.address.full if item.address else None
            print(item.match_kind, address, item.distance_m)

asyncio.run(main())
```

REST:

```
GET /v1/address/reverse?x=127.028601&y=37.500344&crs=EPSG:4326&type=both&zipcode=true&radius_m=200
```

응답은 vworld 호환 envelope인 `response.service`, `response.status`, `response.input`, `response.result[]` 구조다. 각 item은 `type`, `text`, `structure`, `point`, `zipcode`, `zip_source`, `distance_m`를 가진다. 국가지점번호 context는 response-level `response.x_extension.national_point_number`와 `response.x_extension.sppn_makarea[]`에 들어간다.

## 디버깅 UI

`kor-travel-geo-ui`의 `/debug/reverse` 페이지에서 VWorld/MapLibre 지도를 클릭하면 `(lon, lat)` 입력값이 갱신된다. 운영자가 조회 버튼을 누르면 `/v1/address/reverse` 응답을 JSON 뷰어로 확인한다. EXPLAIN으로 인덱스 사용을 확인하려면 `/debug/explain`에서 raw SQL을 붙여 실행한다. 지도 wrapper에서 공통 VWorld/MapLibre 문제가 발견되면 `digitie/maplibre-vworld-js`도 수정 대상에 포함하고, reverse geocode 입력/결과 표시처럼 이 프로젝트 특화 동작은 `kor-travel-geo-ui`에 둔다.

## 알려진 함정

- **좌표 순서**: 외부 인터페이스는 모두 `(lon, lat)`. `(lat, lon)`을 받으면 한국 범위 검증에서 즉시 실패하며, 범위에 우연히 들어맞으면 잘못된 위치를 반환한다(SKILL.md §4-5).
- **`radius_m`이 너무 크면** 노이즈가 늘어 인접 건물이 hit될 수 있다. 기본 200m 권장.
- **`type="road"` 단독 사용**: 반경 내 후보가 도로명을 만들 수 없으면(예: 도로명 키 결측) 빈 결과로 보일 수 있다. 도로명/지번 모두 필요하면 `type="both"`를 쓴다.
- **외부 API 폴백 미적용**: 현재 사양에서 `/v1/address/reverse`는 로컬 결과만 반환한다. vworld의 역지오코딩 폴백이 필요해지면 새 ADR로 결정.
