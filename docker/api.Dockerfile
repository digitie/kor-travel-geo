FROM python:3.12-trixie

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    KTG_API_HOST=0.0.0.0 \
    PORT=12501

WORKDIR /app

# build-essential/gdal for the [loaders] extras; postgresql-client-18 (matches the
# kor_travel_geo server) + zstd for in-process DB restore/backup (pg_restore/pg_dump).
# The PG client comes from the PGDG apt repo so its major tracks the server exactly.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
      build-essential \
      gdal-bin \
      libgdal-dev \
      curl git \
      gnupg \
    && install -d /usr/share/postgresql-common/pgdg \
    && curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc \
         -o /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc \
    && echo "deb [signed-by=/usr/share/postgresql-common/pgdg/apt.postgresql.org.asc] https://apt.postgresql.org/pub/repos/apt $(. /etc/os-release && echo "$VERSION_CODENAME")-pgdg main" \
         > /etc/apt/sources.list.d/pgdg.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends postgresql-client-18 zstd \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md alembic.ini openapi.json ./
COPY alembic ./alembic
COPY sql ./sql
COPY src ./src

# GDAL의 host CPU 기반 병렬 C++ 컴파일이 CPU2·2GiB에서 OOM을 일으켜
# 이 pip 빌드에만 setuptools parallel=1을 적용하고 임시 설정을 같은 layer에서 제거한다.
RUN python -m pip install --upgrade pip \
    && GDAL_VERSION="$(gdal-config --version)" \
    && mkdir /tmp/ktg-gdal-build-home \
    && printf '[build_ext]\nparallel=1\n' > /tmp/ktg-gdal-build-home/.pydistutils.cfg \
    && HOME=/tmp/ktg-gdal-build-home python -m pip install "gdal==${GDAL_VERSION}" \
    && rm /tmp/ktg-gdal-build-home/.pydistutils.cfg \
    && rmdir /tmp/ktg-gdal-build-home \
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

# 최종 runtime interpreter/root로 stdlib cache를 준비한다. 런타임 health에서는 컴파일하지 않는다.
RUN python -I -m kortravelcommon.build_bytecode --stdlib

# public liveness의 응답 헤더 2xx만 확인한다. DB 준비·본문 검증은 /v1/readyz와 별개다.
HEALTHCHECK --interval=30s --timeout=5s --retries=12 --start-period=30s CMD ["sh", "-c", "exec python -I -m kortravelcommon.http_health --port \"${PORT:-12501}\" --path /v1/healthz --timeout-seconds 4"]

EXPOSE 12501

CMD ["sh", "-c", "exec uvicorn kortravelgeo.api.app:app --host ${KTG_API_HOST:-0.0.0.0} --port ${PORT:-12501}"]
