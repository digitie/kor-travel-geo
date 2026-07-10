FROM python:3.12-trixie

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    KTG_API_HOST=0.0.0.0 \
    PORT=12501

WORKDIR /app

# build-essential/gdal for the [loaders] extras; postgresql-client-16 (matches the
# kor_travel_geo server) + zstd for in-process DB restore/backup (pg_restore/pg_dump).
# The PG client comes from the PGDG apt repo so its major tracks the server exactly.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
      build-essential \
      gdal-bin \
      libgdal-dev \
      curl \
      gnupg \
    && install -d /usr/share/postgresql-common/pgdg \
    && curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc \
         -o /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc \
    && echo "deb [signed-by=/usr/share/postgresql-common/pgdg/apt.postgresql.org.asc] https://apt.postgresql.org/pub/repos/apt $(. /etc/os-release && echo "$VERSION_CODENAME")-pgdg main" \
         > /etc/apt/sources.list.d/pgdg.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends postgresql-client-16 zstd \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md alembic.ini openapi.json ./
COPY alembic ./alembic
COPY sql ./sql
COPY src ./src

RUN python -m pip install --upgrade pip \
    && GDAL_VERSION="$(gdal-config --version)" \
    && python -m pip install "gdal==${GDAL_VERSION}" \
    && python -m pip install -e ".[api,loaders]" \
    && python - <<'PY'
import subprocess
from osgeo import gdal

lib_version = subprocess.check_output(["gdal-config", "--version"], text=True).strip()
python_version = gdal.VersionInfo("--version")
print(f"libgdal={lib_version}")
print(f"python_gdal={python_version}")
if lib_version not in python_version:
    raise SystemExit(f"GDAL version mismatch: lib={lib_version}, python={python_version}")
PY

EXPOSE 12501

CMD ["sh", "-c", "uvicorn kortravelgeo.api.app:app --host ${KTG_API_HOST:-0.0.0.0} --port ${PORT:-12501}"]
