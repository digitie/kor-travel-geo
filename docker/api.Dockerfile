FROM python:3.12-trixie

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    KRADDR_GEO_API_HOST=0.0.0.0 \
    PORT=9001

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
      build-essential \
      gdal-bin \
      libgdal-dev \
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

EXPOSE 9001

CMD ["sh", "-c", "uvicorn kraddr.geo.api.app:app --host ${KRADDR_GEO_API_HOST:-0.0.0.0} --port ${PORT:-9001}"]
