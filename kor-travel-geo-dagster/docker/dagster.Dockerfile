# kor-travel-geo independent Dagster runtime (T-290b, ADR-066 §7, dagster-boundary §9).
#
# Build context = the geo repo ROOT (../kor-travel-geo); dockerfile lives under the
# dagster package so it can COPY both the main lib (pyproject/src) and the code-location
# package (kor-travel-geo-dagster/).
#
# T-290j moved loader / full_load_batch EXECUTION into Dagster ops (run_source_loader /
# run_full_load_batch call the main-lib loaders). Those leaves — shp/navi/sppn — use GDAL
# (osgeo) through the `[loaders]` extra, so this image now installs system GDAL and the
# extra, exactly like the API image (docker/api.Dockerfile). The gdal python wheel is
# version-pinned to the libgdal in this image (`gdal==$(gdal-config --version)`); builder
# and runtime install libgdal from the same debian release so the compiled `_gdal` C
# extension finds a matching shared library at import.
#
# One image, two services: the webserver uses the default CMD; the daemon overrides
# `command:` in compose (`dagster-daemon run -m kortravelgeo_dagster.definitions`).

FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    TMPDIR=/tmp \
    TEMP=/tmp \
    TMP=/tmp

WORKDIR /app

# build-essential + gdal-bin/libgdal-dev for the `[loaders]` extra (osgeo builds against
# the libgdal headers here; the version is pinned to gdal-config below).
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
      build-essential curl git gdal-bin libgdal-dev \
    && rm -rf /var/lib/apt/lists/*

# Main library sources (with the [loaders] extra) + the Dagster code-location package.
COPY pyproject.toml README.md ./
COPY src ./src
COPY sql ./sql
COPY kor-travel-geo-dagster ./kor-travel-geo-dagster

# One pip resolve: the explicit gdal==<libgdal> pin constrains the [loaders] extra's
# `gdal>=3.8` to the version matching this image's libgdal. Installing the pin in a SEPARATE
# `pip install` first does not work with --prefix (pip does not see the /install-only gdal as
# already-satisfied, so it re-resolves `gdal>=3.8` to the newest sdist and fails the libgdal
# floor) — they must be in the same invocation.
RUN python -m pip install --upgrade pip \
    && GDAL_VERSION="$(gdal-config --version)" \
    && python -m pip install --prefix=/install \
         "gdal==${GDAL_VERSION}" ".[loaders]" ./kor-travel-geo-dagster

# Fail the build on a GDAL lib/binding version skew (belt-and-suspenders; same check the API
# image runs). osgeo is resolved from the --prefix install tree.
RUN PYTHONPATH="/install/lib/python3.12/site-packages" python - <<'PY'
import subprocess
from osgeo import gdal

lib_version = subprocess.check_output(["gdal-config", "--version"], text=True).strip()
python_version = gdal.VersionInfo("--version")
print(f"libgdal={lib_version}")
print(f"python_gdal={python_version}")
if lib_version not in python_version:
    raise SystemExit(f"GDAL version mismatch: lib={lib_version}, python={python_version}")
PY

FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TMPDIR=/tmp \
    TEMP=/tmp \
    TMP=/tmp \
    DAGSTER_HOME=/opt/dagster/dagster_home

WORKDIR /app

# Runtime system deps:
#  - gdal-bin pulls the libgdal shared library the copied osgeo C extension links against
#    (same debian release as the builder, so the libgdal major matches the built wheel).
#  - the db_backup/db_restore ops shell out to pg_dump/pg_restore + zstd (run_backup_job /
#    run_restore_job), so the PostgreSQL 16 client (matches the kor_travel_geo server) and
#    zstd are installed from the PGDG apt repo.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl gnupg gdal-bin \
    && install -d /usr/share/postgresql-common/pgdg \
    && curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc \
         -o /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc \
    && echo "deb [signed-by=/usr/share/postgresql-common/pgdg/apt.postgresql.org.asc] https://apt.postgresql.org/pub/repos/apt $(. /etc/os-release && echo "$VERSION_CODENAME")-pgdg main" \
         > /etc/apt/sources.list.d/pgdg.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends postgresql-client-16 zstd \
    && apt-get purge -y --auto-remove curl gnupg \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system appuser \
    && useradd --system --gid appuser --home-dir /app --shell /usr/sbin/nologin appuser \
    && mkdir -p "$DAGSTER_HOME" \
    && chown -R appuser:appuser /app /opt/dagster

COPY --from=builder /install /usr/local
COPY --chown=appuser:appuser kor-travel-geo-dagster/docker/dagster.yaml /opt/dagster/dagster_home/dagster.yaml

USER appuser

EXPOSE 12502

CMD ["sh", "-c", "dagster-webserver -m kortravelgeo_dagster.definitions -h 0.0.0.0 -p ${KTG_DAGSTER_PORT:-12502}"]
