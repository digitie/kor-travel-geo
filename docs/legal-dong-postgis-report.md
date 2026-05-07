# Legal-Dong/PostGIS Load Report

Date: 2026-05-08  
Environment: WSL2 Ubuntu, Python 3.12, Docker PostGIS

## Source Data

Legal-dong code source:

- Local file: `/mnt/f/dev/mapplan/dataset/국토교통부_법정동코드_20250805.csv`
- Encoding: CP949
- Columns observed: `법정동코드`, `법정동명`, `폐지여부`
- Rows loaded: `49,861`
- Active rows: `20,555`
- Abolished rows: `29,306`

Public data reference:

- data.go.kr dataset: `국토교통부_전국 법정동_20250807`
- Provider: 국토교통부
- Update cycle: annual
- Next expected registration date on data.go.kr: `2026-08-31`
- The portal describes the dataset as legal regions used by the land
  administration system and sourced from the administrative standard code
  management system.

Boundary ZIP source:

- Directory: `/mnt/f/dev/mapplan/dataset`
- Files:
  - `N3A_G0010000.zip`
  - `N3A_G0100000.zip`
  - `N3A_G0110000.zip`
- SHP attribute code column: `BJCD`
- SHP attribute name column: `NAME`
- Source CRS: Korea 2000 Unified Coordinate System, EPSG:5179-compatible
- Geometry target: PostGIS `MULTIPOLYGON`, SRID `5179`

## Implemented Schema

PostGIS schema name used in validation: `kraddr`

### `legal_dong_codes`

Primary key:

```text
legal_dong_code
```

Important columns:

```text
legal_dong_name
status_name
is_active
previous_legal_dong_code
sido_code
sigungu_code
eup_myeon_dong_code
ri_code
legal_dong_level
source
loaded_at
```

The code segments follow the PDF/code structure:

```text
legal_dong_code(10) = sido(2) + sigungu(3) + eup/myeon/dong(3) + ri(2)
```

### `legal_dong_boundaries`

Primary key:

```text
id
```

FK relationship:

```text
legal_dong_boundaries.legal_dong_code
  -> legal_dong_codes.legal_dong_code
```

`legal_dong_code` is nullable so unmatched boundary source rows can still be
loaded and reported without violating the FK. The original SHP value is always
kept in `source_code`.

Important columns:

```text
legal_dong_code
boundary_level
source_layer
source_file
source_code
source_name
mapping_status
geom
```

Indexes/constraints verified:

```text
fk_boundary_legal_dong_code
uq_boundary_source_layer_code
idx_legal_dong_boundaries_geom
ix_legal_dong_boundaries_legal_code
ix_legal_dong_boundaries_mapping_status
ix_legal_dong_boundaries_source_code
```

### `legal_dong_boundary_mapping_issues`

View for mismatch review. It returns rows where:

- `legal_dong_code IS NULL`
- matched code is inactive/abolished
- `mapping_status <> 'matched'`

## WSL2 Load Command

```bash
cd /mnt/f/dev/pykraddr
python3 -m venv /tmp/pykraddr-venv
source /tmp/pykraddr-venv/bin/activate
python -m pip install -e ".[dev,postgis]"

docker run -d --name pykraddr-postgis \
  -e POSTGRES_PASSWORD=postgres \
  -e POSTGRES_DB=pykraddr \
  -p 55433:5432 \
  postgis/postgis:16-3.4
```

```python
from pathlib import Path
from pykraddr.postgis import PostGISLegalDongStore

url = "postgresql+psycopg://postgres:postgres@localhost:55433/pykraddr"
csv_path = Path("/mnt/f/dev/mapplan/dataset/국토교통부_법정동코드_20250805.csv")
zip_paths = sorted(Path("/mnt/f/dev/mapplan/dataset").glob("N3A_*.zip"))

with PostGISLegalDongStore(url, schema="kraddr") as store:
    store.create_schema()
    store.load_legal_dong_csv(
        csv_path,
        source="data.go.kr 국토교통부_법정동코드_20250805.csv",
        replace=True,
    )
    result = store.load_boundary_zips(zip_paths, replace=True, batch_size=10_000)
    print(result)
    print(store.boundary_mapping_issues(limit=20))
```

## Load Performance Choices

- Legal-dong CSV uses PostgreSQL `COPY FROM STDIN` through `psycopg`.
- Boundary ZIPs are read through GeoPandas. Installing `pyogrio` lets GeoPandas
  use the faster GDAL/Arrow-oriented path when available.
- ZIP extraction happens under WSL2 `/tmp`, not under `/mnt/f`, to avoid slow
  repeated Windows filesystem writes.
- Boundary writes use `GeoDataFrame.to_postgis(..., chunksize=...)`.
- Geometry is normalized to `MULTIPOLYGON` before insert so a single PostGIS
  geometry type can be indexed.
- PostGIS creates the GiST spatial index on `geom`.

For repeated large loads, copy source ZIPs from `/mnt/f/...` into the WSL2 ext4
filesystem first, then load from that path.

## Validation Result

PostGIS version reported:

```text
3.4 USE_GEOS=1 USE_PROJ=1 USE_STATS=1
```

Loaded counts:

```text
legal_dong_codes: 49,861
legal_dong_boundaries: 5,288
FK-mapped boundaries: 5,287
missing legal-dong code boundaries: 1
inactive legal-dong code boundaries: 2
```

Boundary level counts:

```text
sido: 17
sigungu: 264
eup_myeon_dong: 5,007
```

## Mismatch Findings

| Source File | Layer | Source Code | Source Name | Result |
| --- | --- | --- | --- | --- |
| `N3A_G0010000.zip` | `sido` | `3600000000` | 세종특별자치시 | Missing from the 2025 legal-dong CSV |
| `N3A_G0110000.zip` | `eup_myeon_dong` | `2671031000` | 일광면 | Present but `폐지` |
| `N3A_G0110000.zip` | `eup_myeon_dong` | `4784035000` | 금수면 | Present but `폐지` |

### Interpretation

- `3600000000` appears to be a boundary-source sido-level code for
  세종특별자치시, while the current legal-dong CSV contains
  `3611000000` for 세종특별자치시. Do not silently rewrite this code until the
  boundary data provider's code convention is confirmed.
- `2671031000` and `4784035000` satisfy the FK because they exist in the CSV,
  but they are not active legal-dong codes. They are retained with
  `mapping_status='inactive_legal_dong_code'`.

## Recommendation

Keep the nullable FK plus `mapping_status` design. It preserves all GIS source
features, enforces FK integrity when a normalized legal-dong code exists, and
makes source-code drift visible instead of hiding it behind aliases.

If application queries require active-only boundaries, filter with:

```sql
SELECT b.*
FROM kraddr.legal_dong_boundaries AS b
JOIN kraddr.legal_dong_codes AS c
  ON b.legal_dong_code = c.legal_dong_code
WHERE c.is_active IS TRUE
  AND b.mapping_status = 'matched';
```
