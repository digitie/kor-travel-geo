# Address DB schema

The spatial serving schema is centered on one SQLite database.

## `juso_address_points`

Stores all address point candidates.

- `point_id`: stable source-derived key
- `source`: source file or loader name
- `source_dataset`: `location_summary`, `navigation_building`, `navigation_road_section_entrance`
- `source_priority`: lower values win when duplicate candidates exist
- `coordinate_role`: `entrance`, `building_center`, or related role
- `road_name_code`, `underground_yn`, `building_main_no`, `building_sub_no`: exact road-address key
- `legal_dong_code`, `postal_code`
- `road_address`, `building_name`
- `x`, `y`, `srid`
- `geom_wkt`, `geom_wkb`
- `raw_json`: source row details

## `juso_boundary_polygons`

Stores district polygon layers extracted from every SHP in each regional ZIP.

- `source_system`
- `source_file`
- `source_layer`: original SHP stem such as `tl_scco_sig`
- `source_code`
- `source_name`
- `legal_dong_code`
- `boundary_level`
- `mapping_status`
- `geom_wkt`, `geom_wkb`
- `raw_json`

## `juso_spatial_metadata`

Small key/value table for loader timestamps, source names, and operational metadata.

## Alembic

`alembic/versions/0001_spatialite_core.py` creates the core tables and indexes. Geometry columns are added by the runtime store only when SpatiaLite can be loaded.
