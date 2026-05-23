#!/usr/bin/env bash
# Full data load + consistency validation script.
# Run from WSL with Docker PostGIS and data mounted at $DATA_DIR.
#
# Usage:
#   export DATA_DIR=/mnt/f/dev/python-kraddr-geo/data
#   bash scripts/fullload_test.sh
#
# Prerequisites:
#   - docker compose up -d  (PostGIS running on localhost:5432)
#   - pip install -e ".[api,loaders,dev]"
#   - GDAL system libraries installed (gdal-bin libgdal-dev)

set -euo pipefail

DATA_DIR="${DATA_DIR:-/mnt/f/dev/python-kraddr-geo/data}"
PG_DSN="${KRADDR_GEO_PG_DSN:-postgresql+psycopg://addr:addr@localhost:5432/kraddr_geo}"
YYYYMM="${YYYYMM:-202604}"

export KRADDR_GEO_PG_DSN="$PG_DSN"
export KRADDR_GEO_LOADER_DATA_DIR="$DATA_DIR"
export KRADDR_GEO_LOADER_BATCH_SIZE="${BATCH_SIZE:-10000}"

JUSO_DIR="$DATA_DIR/juso"

echo "=== Phase 0: Verify data directories ==="
for d in \
  "$JUSO_DIR/${YYYYMM}_도로명주소 한글_전체분" \
  "$JUSO_DIR/${YYYYMM}_위치정보요약DB_전체분.zip" \
  "$JUSO_DIR/${YYYYMM}_내비게이션용DB_전체분"; do
  if [ ! -e "$d" ]; then
    echo "MISSING: $d"
    exit 1
  fi
done
echo "All required data paths found."

echo ""
echo "=== Phase 1: DDL — create schema + extensions ==="
python -c "
import asyncio
from sqlalchemy import text
from kraddr.geo.infra.engine import make_async_engine
from kraddr.geo.infra.sql import SCHEMA_SQL, INDEX_SQL, iter_sql_statements
from kraddr.geo.settings import Settings

async def main():
    engine = make_async_engine(Settings(pg_dsn='$PG_DSN'))
    async with engine.begin() as conn:
        for sql in iter_sql_statements(SCHEMA_SQL):
            await conn.execute(text(sql))
        for sql in iter_sql_statements(INDEX_SQL):
            try:
                await conn.execute(text(sql))
            except Exception as e:
                print(f'  index warning (may already exist): {e}')
    await engine.dispose()
    print('Schema + indexes created.')

asyncio.run(main())
"

echo ""
echo "=== Phase 2: Text loaders (juso, locsum, navi) ==="
START=$(date +%s)

echo "--- 2a: juso_hangul ---"
python -m kraddr.geo.cli load juso \
  "$JUSO_DIR/${YYYYMM}_도로명주소 한글_전체분" \
  --yyyymm "$YYYYMM"

echo "--- 2b: locsum ---"
python -m kraddr.geo.cli load locsum \
  "$JUSO_DIR/${YYYYMM}_위치정보요약DB_전체분.zip" \
  --yyyymm "$YYYYMM"

echo "--- 2c: navi ---"
python -m kraddr.geo.cli load navi \
  "$JUSO_DIR/${YYYYMM}_내비게이션용DB_전체분" \
  --yyyymm "$YYYYMM"

TEXT_ELAPSED=$(( $(date +%s) - START ))
echo "Text loaders completed in ${TEXT_ELAPSED}s"

echo ""
echo "=== Phase 3: SHP polygons (optional) ==="
SHP_ROOT="$JUSO_DIR/도로명주소 전자지도"
if [ -d "$SHP_ROOT" ]; then
  python -m kraddr.geo.cli load shp-all "$SHP_ROOT" --mode full
else
  echo "SKIP: SHP data not found at $SHP_ROOT"
fi

echo ""
echo "=== Phase 4: Pobox + Bulk (optional) ==="
POBOX="$DATA_DIR/epost/zipcode_full.zip"
if [ -f "$POBOX" ]; then
  python -m kraddr.geo.cli load pobox "$POBOX"
else
  echo "SKIP: pobox data not found at $POBOX"
fi

BULK="$DATA_DIR/epost/bulk_delivery.csv"
if [ -f "$BULK" ]; then
  python -m kraddr.geo.cli load bulk "$BULK"
else
  echo "SKIP: bulk data not found at $BULK"
fi

echo ""
echo "=== Phase 5: Post-load — geometry links + MV refresh ==="
python -m kraddr.geo.cli refresh mv --concurrently

echo ""
echo "=== Phase 6: Row counts ==="
python -c "
import asyncio
from sqlalchemy import text
from kraddr.geo.infra.engine import make_async_engine
from kraddr.geo.settings import Settings

TABLES = [
    'tl_juso_text',
    'tl_locsum_entrc',
    'tl_navi_buld_centroid',
    'tl_navi_entrc',
    'mv_geocode_target',
    'tl_scco_ctprvn',
    'tl_scco_sig',
    'tl_scco_emd',
    'tl_kodis_bas',
    'tl_spbd_buld_polygon',
    'postal_pobox',
    'postal_bulk_delivery',
]

async def main():
    engine = make_async_engine(Settings(pg_dsn='$PG_DSN'))
    async with engine.connect() as conn:
        for table in TABLES:
            try:
                count = await conn.scalar(text(f'SELECT count(*) FROM {table}'))
                print(f'  {table:40s} {count:>12,}')
            except Exception:
                print(f'  {table:40s} (not found)')
    await engine.dispose()

asyncio.run(main())
"

echo ""
echo "=== Phase 7: Consistency check (C1-C10) ==="
python -m kraddr.geo.cli validate consistency --scope full

echo ""
echo "=== Phase 8: Smoke test — geocode + reverse ==="
python -c "
import asyncio
from kraddr.geo.client import AsyncAddressClient
from kraddr.geo.settings import Settings

async def main():
    async with AsyncAddressClient(Settings(pg_dsn='$PG_DSN')) as client:
        # geocode
        r = await client.geocode('서울특별시 종로구 자하문로 94')
        print(f'geocode: status={r.status}, x={r.x}, y={r.y}')
        assert r.status == 'OK', f'geocode failed: {r}'

        # reverse
        if r.x and r.y:
            rev = await client.reverse_geocode(r.x, r.y)
            print(f'reverse: road={rev.road_address}, parcel={rev.parcel_address}')

        # search
        s = await client.search('자하문로')
        print(f'search: total={s.total}, first={s.results[0].address if s.results else None}')

        # zipcode
        z = await client.zipcode(address='서울특별시 종로구 자하문로 94')
        print(f'zipcode: {z.zipcode}')

asyncio.run(main())
"

TOTAL_ELAPSED=$(( $(date +%s) - START ))
echo ""
echo "=== DONE === Total elapsed: ${TOTAL_ELAPSED}s"
