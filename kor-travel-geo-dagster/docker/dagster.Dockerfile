# kor-travel-geo independent Dagster runtime (T-290b, ADR-066 §7, dagster-boundary §9).
#
# Build context = the geo repo ROOT (../kor-travel-geo); dockerfile lives under the
# dagster package so it can COPY both the main lib (pyproject/src) and the code-location
# package (kor-travel-geo-dagster/).
#
# The kortravelgeo_dagster code location consumes only the BASE kortravelgeo library
# (client / settings / loaders.postload.refresh_mv are GDAL-free — verified: loaders
# imports no osgeo). So this image stays on python:3.12-slim and does NOT install GDAL,
# unlike the API image (docker/api.Dockerfile). Keep it that way — do not add the
# [loaders]/[api] extras here unless a future op actually needs them.
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

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential curl git \
    && rm -rf /var/lib/apt/lists/*

# Main library sources (base install, no extras) + the Dagster code-location package.
COPY pyproject.toml README.md ./
COPY src ./src
COPY sql ./sql
COPY kor-travel-geo-dagster ./kor-travel-geo-dagster

RUN python -m pip install --upgrade pip \
    && python -m pip install --prefix=/install . ./kor-travel-geo-dagster

FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TMPDIR=/tmp \
    TEMP=/tmp \
    TMP=/tmp \
    DAGSTER_HOME=/opt/dagster/dagster_home

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
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
