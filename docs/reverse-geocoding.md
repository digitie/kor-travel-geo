# Reverse geocoding

Reverse geocoding is handled by `SpatialiteAddressStore`.

## Local lookup flow

1. Convert request coordinates into the store SRID, default EPSG:5179.
2. Search `juso_address_points` with a bounding box over indexed `x`, `y`.
3. Rank by planar distance, then `source_priority`.
4. Return `ReverseGeocodeResult` with road-address text, legal dong code, postal code, coordinate role, and source dataset.

## Data roles

- 위치정보요약DB is the primary source because it provides entrance-level coordinates with direct road-address keys.
- 내비게이션용DB complements it with building centers, navigation entrances, and road-section entrance rows.
- 구역의 도형 validates whether the candidate point falls inside the expected administrative area and helps diagnose missing or stale codes.

## API example

```python
from kraddr.geo import SpatialiteAddressStore, VWorldLikeReverseGeocodeRequest

with SpatialiteAddressStore("data/juso/kraddr_geo.sqlite") as store:
    result = store.get_address(
        VWorldLikeReverseGeocodeRequest(x=1139887.36, y=1680774.72, crs="EPSG:5179")
    )
```

The synchronous method is local-only. If no local candidate is found and VWorld
credentials are configured, `await store.aget_address(...)` falls back through
`python-vworld-api`'s `AsyncVworldClient`.
