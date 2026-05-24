#!/usr/bin/env bash
# Full data load + consistency validation script.
#
# Workflow:
#   1. Copy data from NTFS to WSL ext4 (avoids cross-filesystem I/O penalty)
#   2. Decompress archives on ext4
#   3. Load into Docker PostGIS (bind-mounted host directories)
#
# Usage:
#   # First time — copy NTFS data to ext4:
#   bash scripts/fullload_test.sh --copy-data
#
#   # Load (data already on ext4):
#   bash scripts/fullload_test.sh
#
#   # Preflight only (no DB commands):
#   PLAN_ONLY=1 bash scripts/fullload_test.sh
#
# Prerequisites:
#   - docker compose -p kraddr-geo-t027 up -d  (PostGIS on localhost:5432)
#   - pip install -e ".[api,loaders,dev]"
#   - GDAL system libraries installed (gdal-bin libgdal-dev)

set -euo pipefail

# --- Paths ---
NTFS_DATA="${NTFS_DATA:-/mnt/f/dev/python-kraddr-geo/data}"
EXT4_DATA="${EXT4_DATA:-$HOME/kraddr-geo-data}"
DATA_DIR="${DATA_DIR:-$EXT4_DATA}"
DB_PORT="${KRADDR_GEO_DB_PORT:-5432}"
PG_DSN="${KRADDR_GEO_PG_DSN:-postgresql+psycopg://addr:addr@localhost:${DB_PORT}/kraddr_geo}"
JUSO_YYYYMM="${JUSO_YYYYMM:-${YYYYMM:-202603}}"
LOCSUM_YYYYMM="${LOCSUM_YYYYMM:-${YYYYMM:-202604}}"
NAVI_YYYYMM="${NAVI_YYYYMM:-${YYYYMM:-202604}}"
PLAN_ONLY="${PLAN_ONLY:-0}"
COPY_DATA="${COPY_DATA:-0}"

export KRADDR_GEO_PG_DSN="$PG_DSN"
export KRADDR_GEO_LOADER_DATA_DIR="$DATA_DIR"
export KRADDR_GEO_LOADER_BATCH_SIZE="${BATCH_SIZE:-10000}"
export KRADDR_GEO_PG_STATEMENT_TIMEOUT_MS="${KRADDR_GEO_PG_STATEMENT_TIMEOUT_MS:-1800000}"

log() {
  printf '\n[%s] %s\n' "$(date -Is)" "$*"
}

run() {
  log "RUN: $*"
  if [ "$PLAN_ONLY" = "1" ]; then
    return 0
  fi
  "$@"
}

# --- Handle --copy-data flag ---
for arg in "$@"; do
  if [ "$arg" = "--copy-data" ]; then
    COPY_DATA=1
  fi
done

# === Phase -1: Copy NTFS → ext4 ===
if [ "$COPY_DATA" = "1" ]; then
  log "=== Phase -1: Copy NTFS data to ext4 ==="
  echo "  Source (NTFS): $NTFS_DATA"
  echo "  Target (ext4): $EXT4_DATA"

  mkdir -p "$EXT4_DATA/juso" "$EXT4_DATA/epost" "$EXT4_DATA/pgdata"

  JUSO_SRC="$NTFS_DATA/juso"

  log "Copying juso text (한글 전체분)..."
  cp -ru "$JUSO_SRC/${JUSO_YYYYMM}_도로명주소 한글_전체분" "$EXT4_DATA/juso/" 2>/dev/null || true

  log "Copying locsum ZIP..."
  cp -u "$JUSO_SRC/${LOCSUM_YYYYMM}_위치정보요약DB_전체분.zip" "$EXT4_DATA/juso/" 2>/dev/null || true

  log "Copying navi..."
  if [ -d "$JUSO_SRC/${NAVI_YYYYMM}_내비게이션용DB_전체분" ]; then
    cp -ru "$JUSO_SRC/${NAVI_YYYYMM}_내비게이션용DB_전체분" "$EXT4_DATA/juso/"
  elif [ -f "$JUSO_SRC/${NAVI_YYYYMM}_내비게이션용DB_전체분.7z" ]; then
    log "Extracting navi 7z archive..."
    mkdir -p "$EXT4_DATA/juso/${NAVI_YYYYMM}_내비게이션용DB_전체분"
    7z x -o"$EXT4_DATA/juso/${NAVI_YYYYMM}_내비게이션용DB_전체분" \
      "$JUSO_SRC/${NAVI_YYYYMM}_내비게이션용DB_전체분.7z" -aoa
  fi

  log "Copying SHP (전자지도)..."
  if [ -d "$JUSO_SRC/도로명주소 전자지도" ]; then
    cp -ru "$JUSO_SRC/도로명주소 전자지도" "$EXT4_DATA/juso/"
  fi

  log "Copying epost data..."
  cp -u "$NTFS_DATA/epost/"*.zip "$EXT4_DATA/epost/" 2>/dev/null || true
  cp -u "$NTFS_DATA/epost/"*.csv "$EXT4_DATA/epost/" 2>/dev/null || true

  log "Disk usage after copy:"
  du -sh "$EXT4_DATA"/* 2>/dev/null || true
  df -h "$EXT4_DATA"
  log "Copy complete. Re-run without --copy-data to start loading."
  exit 0
fi

# --- Resolve paths ---
JUSO_DIR="$DATA_DIR/juso"
JUSO_TEXT_DIR="$JUSO_DIR/${JUSO_YYYYMM}_도로명주소 한글_전체분"
LOCSUM_ZIP="$JUSO_DIR/${LOCSUM_YYYYMM}_위치정보요약DB_전체분.zip"
NAVI_DIR="$JUSO_DIR/${NAVI_YYYYMM}_내비게이션용DB_전체분"
SHP_ROOT="$JUSO_DIR/도로명주소 전자지도"

log "=== Preflight: tool versions ==="
python --version
if command -v gdalinfo >/dev/null 2>&1; then
  gdalinfo --version
else
  echo "WARNING: gdalinfo not found. SHP loading (Phase 3) will fail."
  echo "  Install with: sudo apt-get install -y gdal-bin libgdal-dev"
  if [ -d "$SHP_ROOT" ]; then
    echo "  SHP data exists at $SHP_ROOT — GDAL is required."
    exit 1
  fi
fi

log "=== Preflight: disk space ==="
df -h "$DATA_DIR"

log "=== Phase 0: Verify data directories ==="
for d in \
  "$JUSO_TEXT_DIR" \
  "$LOCSUM_ZIP" \
  "$NAVI_DIR"; do
  if [ ! -e "$d" ]; then
    echo "MISSING: $d"
    exit 1
  fi
done
echo "All required data paths found."
echo "  DATA_DIR=$DATA_DIR"
echo "  JUSO_YYYYMM=$JUSO_YYYYMM"
echo "  LOCSUM_YYYYMM=$LOCSUM_YYYYMM"
echo "  NAVI_YYYYMM=$NAVI_YYYYMM"
echo "  PG_DSN=$PG_DSN"

if [ "$PLAN_ONLY" = "1" ]; then
  log "PLAN_ONLY=1: data path preflight finished; no database/load commands executed."
  exit 0
fi

log "=== Phase 1: DDL — kraddr-geo init-db ==="
run kraddr-geo init-db

log "=== Phase 2: Text loaders (juso, locsum, navi) ==="
START=$(date +%s)

echo "--- 2a: juso_hangul ---"
run kraddr-geo load juso "$JUSO_TEXT_DIR" --yyyymm "$JUSO_YYYYMM"

echo "--- 2b: locsum ---"
run kraddr-geo load locsum "$LOCSUM_ZIP" --yyyymm "$LOCSUM_YYYYMM"

echo "--- 2c: navi ---"
run kraddr-geo load navi "$NAVI_DIR" --yyyymm "$NAVI_YYYYMM"

TEXT_ELAPSED=$(( $(date +%s) - START ))
echo "Text loaders completed in ${TEXT_ELAPSED}s"

log "=== Phase 3: SHP polygons (optional) ==="
if [ -d "$SHP_ROOT" ]; then
  run kraddr-geo load shp-all "$SHP_ROOT" --mode full
else
  echo "SKIP: SHP data not found at $SHP_ROOT"
fi

log "=== Phase 4: Pobox + Bulk (optional) ==="
POBOX="$DATA_DIR/epost/zipcode_full.zip"
if [ -f "$POBOX" ]; then
  run kraddr-geo load pobox "$POBOX"
else
  echo "SKIP: pobox data not found at $POBOX"
fi

BULK="$DATA_DIR/epost/bulk_delivery.csv"
if [ -f "$BULK" ]; then
  run kraddr-geo load bulk "$BULK"
else
  echo "SKIP: bulk data not found at $BULK"
fi

log "=== Phase 5: Post-load — geometry links + MV refresh ==="
python - <<'PY'
import asyncio

from kraddr.geo.client import AsyncAddressClient
from kraddr.geo.loaders.postload import resolve_text_geometry_links


async def main() -> None:
    async with AsyncAddressClient() as client:
        assert client.engine is not None
        await resolve_text_geometry_links(client.engine)
        print("resolved text geometry links")


asyncio.run(main())
PY
run kraddr-geo refresh mv --swap

log "=== Phase 6: Row counts ==="
python - <<'PY'
import asyncio
from sqlalchemy import text
from kraddr.geo.infra.engine import make_async_engine
from kraddr.geo.settings import get_settings

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
    engine = make_async_engine(get_settings())
    async with engine.connect() as conn:
        for table in TABLES:
            try:
                count = await conn.scalar(text(f'SELECT count(*) FROM {table}'))
                print(f'  {table:40s} {count:>12,}')
            except Exception:
                print(f'  {table:40s} (not found)')
    await engine.dispose()

asyncio.run(main())
PY

log "=== Phase 7: Consistency check (C1-C10) ==="
run kraddr-geo validate consistency --scope full

log "=== Phase 8: Smoke test — geocode + reverse ==="
python - <<'PY'
import asyncio
from kraddr.geo.client import AsyncAddressClient

async def main():
    async with AsyncAddressClient() as client:
        # geocode
        r = await client.geocode('서울특별시 종로구 자하문로 94')
        point = r.result.point if r.result else None
        print(f'geocode: status={r.status}, point={point}')
        assert r.status == 'OK', f'geocode failed: {r}'

        # reverse
        if point:
            rev = await client.reverse_geocode(point.x, point.y)
            print(f'reverse: status={rev.status}, count={len(rev.result)}')

        # search
        s = await client.search('자하문로')
        print(f'search: status={s.status}, total={s.total}, first={s.result[0].address if s.result else None}')

        # zipcode
        z = await client.zipcode(address='서울특별시 종로구 자하문로 94')
        print(f'zipcode: status={z.status}, first={z.result[0].zip_no if z.result else None}')

asyncio.run(main())
PY

TOTAL_ELAPSED=$(( $(date +%s) - START ))
log "=== DONE === Total elapsed: ${TOTAL_ELAPSED}s"
