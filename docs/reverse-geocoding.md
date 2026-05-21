# Reverse geocoding

Reverse geocoding은 `SpatialiteAddressStore`가 담당한다.

## 로컬 조회 흐름

1. 요청 좌표를 store SRID로 변환한다. 기본값은 EPSG:5179다.
2. `juso_address_points`에서 `x`, `y` index를 활용한 bounding box 후보를 찾는다.
3. 평면 거리와 `source_priority`를 기준으로 후보를 정렬한다.
4. 도로명주소, 법정동 코드, 우편번호, 좌표 역할, 원천 dataset을 담은 `ReverseGeocodeResult`를 반환한다.

## 데이터 역할

- 위치정보요약DB는 도로명주소 key와 직접 연결된 출입구 좌표를 제공하므로 기본 원천이다.
- 내비게이션용DB는 건물 중심, 내비게이션 출입구, 도로 구간 출입구 row로 보완한다.
- 구역의 도형은 후보 좌표가 기대 행정구역 안에 있는지 검증하고 누락/오래된 코드를 진단하는 데 쓴다.

## API 예시

```python
from kraddr.geo import SpatialiteAddressStore, AddressReverseGeocodeRequest

with SpatialiteAddressStore("data/juso/kraddr_geo.sqlite") as store:
    result = store.get_address(
        AddressReverseGeocodeRequest(x=1139887.36, y=1680774.72, crs="EPSG:5179")
    )
```

로컬 후보를 찾지 못했고 VWorld credential이 설정되어 있으면 같은 method가 `python-vworld-api` fallback을 호출할 수 있다.
