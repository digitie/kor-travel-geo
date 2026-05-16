# Geocoding readiness

The current implementation is ready for local geocoding/reverse geocoding once the Juso ZIP/TXT datasets are loaded into `juso_address_points`.

## Strong inputs

- 위치정보요약DB: highest-value input for entrance-level coordinates.
- 내비게이션용DB: useful for building-center fallback and navigation-style matching.
- 구역의 도형: useful for containment checks, legal-dong validation, and gap reports.
- 도로명주소/관련지번 SQLite: useful for address text and related jibun enrichment.

## Known gaps

- SpatiaLite extension availability varies by machine. The store still works with plain indexed columns, but polygon spatial predicates need the extension or Shapely-side evaluation.
- Some district SHP layers are administrative or service zones rather than direct legal-dong polygons, so `mapping_status` remains `unverified` until cross-checked.
- Road-name fuzzy search still needs a normalization layer for spacing, building aliases, and older address forms.
- Live VWorld fallback requires API credentials and should be rate-limited in production.

## Validation checklist

- Load full 위치정보요약DB and confirm row count.
- Load at least one regional 내비게이션용DB file and compare shared road-address keys.
- Load all 17 regional 구역의 도형 ZIPs and count seven layers per region.
- Run `EXPLAIN QUERY PLAN` for road key, postal code, and nearest-neighbor candidate queries.
- Compare python-krmois-api sample addresses against local geocoding and reverse geocoding.
