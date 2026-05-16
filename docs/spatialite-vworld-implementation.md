# SpatiaLite and VWorld-compatible geocoding plan

This implementation uses SQLite as the default database and enables SpatiaLite when the local extension is available. The same tables keep plain `x`, `y`, WKT, and WKB values so the library remains usable on machines where the extension cannot be loaded.

## Data priority

1. `location_summary`: authoritative Juso entrance coordinates from 위치정보요약DB.
2. `navigation_building`: building center and entrance coordinates from 내비게이션용DB.
3. `navigation_road_section_entrance`: road-section entrance support rows.
4. `juso_boundary_shapes`: district polygons for containment checks and administrative validation.
5. `rnaddrkor.sqlite`: existing road-name address attributes and related jibun data.

## Tables

- `juso_address_points`: geocoding/reverse-geocoding candidate points.
- `juso_boundary_polygons`: district polygon WKT/WKB and source metadata.
- `juso_spatial_metadata`: loader metadata and operational notes.

The point table stores `source_priority`, `coordinate_role`, road-name key columns, legal dong code, postal code, source address text, EPSG:5179 coordinates, and raw source JSON.

## Indexing

The core lookup indexes are:

- `(road_name_code, underground_yn, building_main_no, building_sub_no)` for exact road-address key lookup.
- `postal_code` for 우편번호 search.
- `(x, y)` for bounded nearest-neighbor scans.
- `legal_dong_code`, `source_dataset`, `coordinate_role`, and `source_priority` for filtering.
- Boundary source/layer/code and legal-dong indexes for polygon validation.

When SpatiaLite is available, geometry columns and spatial indexes are added in place.

## VWorld-compatible surface

`SpatialiteAddressStore.get_coord()` accepts `VWorldLikeGeocodeRequest`.
`SpatialiteAddressStore.get_address()` accepts `VWorldLikeReverseGeocodeRequest`.
`lookup_postal_code()` accepts `PostalCodeLookupRequest`.

If local candidates are missing and a VWorld key/domain is configured, the store calls `python-vworld-api` and normalizes the response into the same candidate DTOs.
