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
SHP_YYYYMM="${SHP_YYYYMM:-${YYYYMM:-202604}}"
ROADADDR_ENTRANCE_YYYYMM="${ROADADDR_ENTRANCE_YYYYMM:-202605}"
SPPN_MAKAREA_YYYYMM="${SPPN_MAKAREA_YYYYMM:-202605}"
DAILY_JUSO_ZIP="${DAILY_JUSO_ZIP:-}"
DAILY_YYYYMM="${DAILY_YYYYMM:-}"
PLAN_ONLY="${PLAN_ONLY:-0}"
COPY_DATA="${COPY_DATA:-0}"
PYTHON_BIN="${PYTHON:-python}"
KRADDR_GEO_BIN="${KRADDR_GEO_BIN:-kraddr-geo}"

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

  log "Copying roadaddr entrance ZIPs..."
  if [ -d "$JUSO_SRC/도로명주소 출입구 정보" ]; then
    cp -ru "$JUSO_SRC/도로명주소 출입구 정보" "$EXT4_DATA/juso/"
  fi

  log "Copying zone shape ZIPs..."
  if [ -d "$JUSO_SRC/구역의 도형" ]; then
    cp -ru "$JUSO_SRC/구역의 도형" "$EXT4_DATA/juso/"
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
ROADADDR_ENTRANCE_DIR="$JUSO_DIR/도로명주소 출입구 정보"
SPPN_MAKAREA_DIR="$JUSO_DIR/구역의 도형"

log "=== Preflight: tool versions ==="
"$PYTHON_BIN" --version
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
if command -v docker >/dev/null 2>&1; then
  docker --version
fi

log "=== Preflight: system status ==="
uname -a
if command -v lscpu >/dev/null 2>&1; then
  lscpu | sed -n '1,20p'
fi
if command -v free >/dev/null 2>&1; then
  free -h
fi

log "=== Preflight: disk space ==="
df -h "$DATA_DIR" /

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
echo "  SHP_YYYYMM=$SHP_YYYYMM"
echo "  ROADADDR_ENTRANCE_YYYYMM=$ROADADDR_ENTRANCE_YYYYMM"
echo "  SPPN_MAKAREA_YYYYMM=$SPPN_MAKAREA_YYYYMM"
echo "  DAILY_JUSO_ZIP=${DAILY_JUSO_ZIP:-'(not set; daily delta skipped)'}"
echo "  DAILY_YYYYMM=${DAILY_YYYYMM:-'(infer from delta file)'}"
echo "  PG_DSN=$PG_DSN"
echo "  KRADDR_GEO_DB_PORT=$DB_PORT (used only when KRADDR_GEO_PG_DSN is unset)"
if [ -d "$ROADADDR_ENTRANCE_DIR" ]; then
  echo "  ROADADDR_ENTRANCE_DIR=$ROADADDR_ENTRANCE_DIR"
else
  echo "  ROADADDR_ENTRANCE_DIR missing; optional direct entrance load will be skipped"
fi
if [ -d "$SPPN_MAKAREA_DIR" ]; then
  echo "  SPPN_MAKAREA_DIR=$SPPN_MAKAREA_DIR"
else
  echo "  SPPN_MAKAREA_DIR missing; optional SPPN makarea load will be skipped"
fi
if [ -n "$DAILY_JUSO_ZIP" ] && [ ! -f "$DAILY_JUSO_ZIP" ]; then
  echo "MISSING: DAILY_JUSO_ZIP=$DAILY_JUSO_ZIP"
  exit 1
fi

if [ "$PLAN_ONLY" = "1" ]; then
  log "PLAN_ONLY=1: data path preflight finished; no database/load commands executed."
  exit 0
fi

TOTAL_START=$(date +%s)

log "=== Phase 1: DDL — kraddr-geo init-db ==="
PHASE_START=$(date +%s)
run "$KRADDR_GEO_BIN" init-db
DDL_ELAPSED=$(( $(date +%s) - PHASE_START ))
echo "DDL/init-db completed in ${DDL_ELAPSED}s"

log "=== Phase 2: Text loaders (juso, locsum, navi) ==="
TEXT_START=$(date +%s)

echo "--- 2a: juso_hangul ---"
PHASE_START=$(date +%s)
run "$KRADDR_GEO_BIN" load juso "$JUSO_TEXT_DIR" --yyyymm "$JUSO_YYYYMM"
JUSO_ELAPSED=$(( $(date +%s) - PHASE_START ))
echo "juso_hangul completed in ${JUSO_ELAPSED}s"

echo "--- 2b: parcel links ---"
PHASE_START=$(date +%s)
run "$KRADDR_GEO_BIN" load parcel-links "$JUSO_TEXT_DIR" --yyyymm "$JUSO_YYYYMM"
PARCEL_LINK_ELAPSED=$(( $(date +%s) - PHASE_START ))
echo "parcel_links completed in ${PARCEL_LINK_ELAPSED}s"

echo "--- 2c: locsum ---"
PHASE_START=$(date +%s)
run "$KRADDR_GEO_BIN" load locsum "$LOCSUM_ZIP" --yyyymm "$LOCSUM_YYYYMM"
LOCSUM_ELAPSED=$(( $(date +%s) - PHASE_START ))
echo "locsum completed in ${LOCSUM_ELAPSED}s"

echo "--- 2d: navi ---"
PHASE_START=$(date +%s)
run "$KRADDR_GEO_BIN" load navi "$NAVI_DIR" --yyyymm "$NAVI_YYYYMM"
NAVI_ELAPSED=$(( $(date +%s) - PHASE_START ))
echo "navi completed in ${NAVI_ELAPSED}s"

TEXT_ELAPSED=$(( $(date +%s) - TEXT_START ))
echo "Text loaders completed in ${TEXT_ELAPSED}s (juso=${JUSO_ELAPSED}s, parcel_links=${PARCEL_LINK_ELAPSED}s, locsum=${LOCSUM_ELAPSED}s, navi=${NAVI_ELAPSED}s)"

log "=== Phase 3: SHP polygons (optional) ==="
PHASE_START=$(date +%s)
if [ -d "$SHP_ROOT" ]; then
  run "$KRADDR_GEO_BIN" load shp-all "$SHP_ROOT" --mode full --yyyymm "$SHP_YYYYMM"
else
  echo "SKIP: SHP data not found at $SHP_ROOT"
fi
SHP_ELAPSED=$(( $(date +%s) - PHASE_START ))
echo "SHP phase completed in ${SHP_ELAPSED}s"

log "=== Phase 3b: Optional direct entrance + SPPN makarea ==="
PHASE_START=$(date +%s)
if [ -d "$ROADADDR_ENTRANCE_DIR" ]; then
  run "$KRADDR_GEO_BIN" load roadaddr-entrances "$ROADADDR_ENTRANCE_DIR" --yyyymm "$ROADADDR_ENTRANCE_YYYYMM"
else
  echo "SKIP: roadaddr entrance data not found at $ROADADDR_ENTRANCE_DIR"
fi
ROADADDR_ENTRANCE_ELAPSED=$(( $(date +%s) - PHASE_START ))
echo "roadaddr entrance phase completed in ${ROADADDR_ENTRANCE_ELAPSED}s"

PHASE_START=$(date +%s)
if [ -d "$SPPN_MAKAREA_DIR" ]; then
  run "$KRADDR_GEO_BIN" load sppn-makarea "$SPPN_MAKAREA_DIR" --yyyymm "$SPPN_MAKAREA_YYYYMM"
else
  echo "SKIP: SPPN makarea data not found at $SPPN_MAKAREA_DIR"
fi
SPPN_MAKAREA_ELAPSED=$(( $(date +%s) - PHASE_START ))
echo "SPPN makarea phase completed in ${SPPN_MAKAREA_ELAPSED}s"

log "=== Phase 3c: Daily delta (optional) ==="
PHASE_START=$(date +%s)
if [ -n "$DAILY_JUSO_ZIP" ]; then
  DAILY_ARGS=("$DAILY_JUSO_ZIP")
  if [ -n "$DAILY_YYYYMM" ]; then
    DAILY_ARGS+=("--yyyymm" "$DAILY_YYYYMM")
  fi
  run "$KRADDR_GEO_BIN" load daily-juso "${DAILY_ARGS[@]}"
  run "$KRADDR_GEO_BIN" load daily-parcel-links "${DAILY_ARGS[@]}"
else
  echo "SKIP: DAILY_JUSO_ZIP is not set"
fi
DAILY_ELAPSED=$(( $(date +%s) - PHASE_START ))
echo "daily delta phase completed in ${DAILY_ELAPSED}s"

log "=== Phase 4: Pobox + Bulk (optional) ==="
POBOX="$DATA_DIR/epost/zipcode_full.zip"
if [ -f "$POBOX" ]; then
  run "$KRADDR_GEO_BIN" load pobox "$POBOX"
else
  echo "SKIP: pobox data not found at $POBOX"
fi

BULK="$DATA_DIR/epost/bulk_delivery.csv"
if [ -f "$BULK" ]; then
  run "$KRADDR_GEO_BIN" load bulk "$BULK"
else
  echo "SKIP: bulk data not found at $BULK"
fi

log "=== Phase 5: Post-load — geometry links + MV refresh ==="
PHASE_START=$(date +%s)
"$PYTHON_BIN" - <<'PY'
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
LINK_ELAPSED=$(( $(date +%s) - PHASE_START ))
echo "geometry link resolution completed in ${LINK_ELAPSED}s"

PHASE_START=$(date +%s)
run "$KRADDR_GEO_BIN" refresh mv --swap
MV_ELAPSED=$(( $(date +%s) - PHASE_START ))
echo "MV swap refresh completed in ${MV_ELAPSED}s"

log "=== Phase 6: Row counts ==="
"$PYTHON_BIN" - <<'PY'
import asyncio
from sqlalchemy import text
from kraddr.geo.infra.engine import make_async_engine
from kraddr.geo.settings import get_settings

TABLES = [
    'tl_juso_text',
    'tl_juso_parcel_link',
    'tl_locsum_entrc',
    'tl_roadaddr_entrc',
    'tl_navi_buld_centroid',
    'tl_navi_entrc',
    'tl_sppn_makarea',
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
run "$KRADDR_GEO_BIN" validate consistency --scope full

log "=== Phase 8: Smoke test — geocode + reverse ==="
"$PYTHON_BIN" - <<'PY'
import asyncio
from kraddr.geo.client import AsyncAddressClient

async def main():
    async with AsyncAddressClient() as client:
        # geocode
        r = await client.geocode(query='서울특별시 종로구 자하문로 94')
        first = r.candidates[0] if r.candidates else None
        point = first.point if first else None
        print(f'geocode: status={r.status}, candidates={len(r.candidates)}, point={point}')
        assert r.status == 'OK' and point is not None, f'geocode failed: {r}'

        # reverse
        rev = await client.reverse(point.x, point.y)
        print(f'reverse: status={rev.status}, count={len(rev.candidates)}')

        # search
        s = await client.search('자하문로')
        search_first = s.candidates[0].address.full if s.candidates and s.candidates[0].address else None
        print(f'search: status={s.status}, total={s.total}, first={search_first}')

        # zipcode
        z = await client.zipcode(address='서울특별시 종로구 자하문로 94')
        print(f'zipcode: status={z.status}, first={z.result[0].zip_no if z.result else None}')

asyncio.run(main())
PY

TOTAL_ELAPSED=$(( $(date +%s) - TOTAL_START ))
log "=== DONE === Total elapsed: ${TOTAL_ELAPSED}s"
