#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
UI_DIR="$ROOT_DIR/kor-travel-geo-ui"

API_IMAGE="${KTG_API_IMAGE:-kor-travel-geo-api:latest-main-gdal}"
UI_IMAGE="${KTG_UI_IMAGE:-kor-travel-geo-ui:latest-main}"
API_CONTAINER="${KTG_API_CONTAINER:-kor-travel-geo-api-latest}"
UI_CONTAINER="${KTG_UI_CONTAINER:-kor-travel-geo-ui-latest}"
RESTART_POLICY="${KTG_DOCKER_RESTART_POLICY:-unless-stopped}"
NETWORK_MODE="${KTG_DOCKER_NETWORK_MODE:-bridge}"
NETWORK_NAME="${KTG_DOCKER_NETWORK:-kor-travel-geo-net}"
HOST_GATEWAY="${KTG_DOCKER_HOST_GATEWAY:-host.docker.internal}"

API_HOST_PORT="${KTG_API_PORT:-12201}"
API_CONTAINER_PORT="${KTG_API_CONTAINER_PORT:-12201}"
UI_HOST_PORT="${KTG_UI_PORT:-12205}"
UI_CONTAINER_PORT="${KTG_UI_CONTAINER_PORT:-12205}"
DB_PORT="${KTG_DB_PORT:-5432}"
DATA_DIR="${KTG_DOCKER_DATA_DIR:-${DATA_DIR:-/mnt/f/dev/kor-travel-geo/data}}"

if [[ "$NETWORK_MODE" == "host" ]]; then
  DEFAULT_PG_HOST="127.0.0.1"
  DEFAULT_UI_API_URL="http://127.0.0.1:${API_CONTAINER_PORT}"
  DEFAULT_RUSTFS_ENDPOINT="http://127.0.0.1:12101"
else
  DEFAULT_PG_HOST="$HOST_GATEWAY"
  DEFAULT_UI_API_URL="http://kor-travel-geo-api:${API_CONTAINER_PORT}"
  DEFAULT_RUSTFS_ENDPOINT="http://${HOST_GATEWAY}:12101"
fi

DEFAULT_PG_DSN="postgresql+psycopg://addr:addr@${DEFAULT_PG_HOST}:${DB_PORT}/kor_travel_geo"
PG_DSN="${KTG_DOCKER_PG_DSN:-${KTG_PG_DSN:-$DEFAULT_PG_DSN}}"
UI_API_INTERNAL_URL="${KTG_API_INTERNAL_URL:-$DEFAULT_UI_API_URL}"
RUSTFS_ENABLED="${KTG_RUSTFS_ENABLED:-0}"
RUSTFS_ENDPOINT_URL="${KTG_RUSTFS_ENDPOINT_URL:-$DEFAULT_RUSTFS_ENDPOINT}"
RUSTFS_BUCKET="${KTG_RUSTFS_BUCKET:-kor-travel-geo}"
RUSTFS_PREFIX="${KTG_RUSTFS_PREFIX:-kor-travel-geo}"
RUSTFS_REGION="${KTG_RUSTFS_REGION:-us-east-1}"

usage() {
  cat <<'EOF'
Usage:
  scripts/docker_app.sh build-api
  scripts/docker_app.sh build-ui
  scripts/docker_app.sh build
  scripts/docker_app.sh up-api
  scripts/docker_app.sh up-ui
  scripts/docker_app.sh up
  scripts/docker_app.sh down
  scripts/docker_app.sh status
  scripts/docker_app.sh logs [api|ui]
  scripts/docker_app.sh cli <command> [args...]
  scripts/docker_app.sh load <ktgctl load args...>
  scripts/docker_app.sh load-full-set [extra ktgctl load full-set args...]

This script only starts kor-travel-geo API/UI containers.
PostgreSQL and RustFS must already be running somewhere reachable. Store their
connection settings in this project via .env or process environment variables.

Important env:
  KTG_DOCKER_PG_DSN=postgresql+psycopg://addr:addr@host.docker.internal:5432/kor_travel_geo
  KTG_RUSTFS_ENABLED=1
  KTG_RUSTFS_ENDPOINT_URL=http://host.docker.internal:12101
  KTG_RUSTFS_BUCKET=kor-travel-geo
  KTG_RUSTFS_PREFIX=kor-travel-geo
  KTG_RUSTFS_ACCESS_KEY=<access key>
  KTG_RUSTFS_SECRET_KEY=<secret key>
  KTG_DOCKER_DATA_DIR=/mnt/f/dev/kor-travel-geo/data
  KTG_DOCKER_RESTART_POLICY=unless-stopped   # set to "no" to disable
  KTG_VWORLD_API_KEY=<runtime key>
EOF
}

log() {
  printf '[docker-app] %s\n' "$*"
}

require_docker() {
  if ! command -v docker >/dev/null 2>&1; then
    echo "docker not found" >&2
    exit 127
  fi
}

dotenv_get() {
  local key="$1"
  local file line value
  for file in "$ROOT_DIR/.env" "$UI_DIR/.env.local"; do
    [[ -f "$file" ]] || continue
    line="$(grep -E "^[[:space:]]*${key}[[:space:]]*=" "$file" | tail -n 1 || true)"
    [[ -n "$line" ]] || continue
    value="${line#*=}"
    value="${value%%#*}"
    value="$(printf '%s' "$value" | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//')"
    value="${value%\"}"
    value="${value#\"}"
    value="${value%\'}"
    value="${value#\'}"
    if [[ -n "$value" ]]; then
      printf '%s' "$value"
      return 0
    fi
  done
  return 1
}

resolve_vworld_key() {
  if [[ -n "${KTG_VWORLD_API_KEY:-}" ]]; then
    printf '%s' "$KTG_VWORLD_API_KEY"
    return 0
  fi
  if dotenv_get KTG_VWORLD_API_KEY; then
    return 0
  fi
  if [[ -n "${NEXT_PUBLIC_VWORLD_API_KEY:-}" ]]; then
    printf '%s' "$NEXT_PUBLIC_VWORLD_API_KEY"
    return 0
  fi
  dotenv_get NEXT_PUBLIC_VWORLD_API_KEY || true
}

resolve_env_or_dotenv() {
  local key="$1"
  local default_value="$2"
  local current_value="${!key:-}"
  if [[ -n "$current_value" ]]; then
    printf '%s' "$current_value"
    return 0
  fi
  if dotenv_get "$key"; then
    return 0
  fi
  printf '%s' "$default_value"
}

ensure_network() {
  [[ "$NETWORK_MODE" != "host" ]] || return 0
  if ! docker network inspect "$NETWORK_NAME" >/dev/null 2>&1; then
    log "creating docker network: $NETWORK_NAME"
    docker network create "$NETWORK_NAME" >/dev/null
  fi
}

remove_container() {
  local name="$1"
  if docker ps -a --format '{{.Names}}' | grep -Fxq "$name"; then
    log "removing existing container: $name"
    docker rm -f "$name" >/dev/null
  fi
}

free_host_port() {
  local port="$1"
  local docker_ids pids

  docker_ids="$(docker ps --filter "publish=${port}" --format '{{.ID}}' || true)"
  if [[ -n "$docker_ids" ]]; then
    log "removing containers publishing host port ${port}"
    # shellcheck disable=SC2086
    docker rm -f $docker_ids >/dev/null
  fi

  pids=""
  if command -v lsof >/dev/null 2>&1; then
    pids="$(lsof -tiTCP:"$port" -sTCP:LISTEN || true)"
  elif command -v fuser >/dev/null 2>&1; then
    pids="$(fuser -n tcp "$port" 2>/dev/null || true)"
  fi
  if [[ -n "$pids" ]]; then
    log "stopping processes listening on host port ${port}: ${pids//$'\n'/ }"
    # shellcheck disable=SC2086
    kill $pids 2>/dev/null || true
    sleep 1
    # shellcheck disable=SC2086
    kill -9 $pids 2>/dev/null || true
  fi
}

build_api() {
  require_docker
  log "building API image: $API_IMAGE"
  docker build -f "$ROOT_DIR/docker/api.Dockerfile" -t "$API_IMAGE" "$ROOT_DIR"
}

build_ui() {
  require_docker
  log "building UI image: $UI_IMAGE"
  docker build -t "$UI_IMAGE" "$UI_DIR"
}

run_api() {
  require_docker
  ensure_network
  remove_container "$API_CONTAINER"
  free_host_port "$API_HOST_PORT"

  local vworld_key rustfs_access_key rustfs_secret_key
  vworld_key="$(resolve_vworld_key)"
  rustfs_access_key="$(resolve_env_or_dotenv KTG_RUSTFS_ACCESS_KEY "")"
  rustfs_secret_key="$(resolve_env_or_dotenv KTG_RUSTFS_SECRET_KEY "")"

  local args=(run -d --name "$API_CONTAINER" --restart "$RESTART_POLICY")
  if [[ "$NETWORK_MODE" == "host" ]]; then
    args+=(--network host)
  else
    args+=(--network "$NETWORK_NAME" --network-alias kor-travel-geo-api --add-host "${HOST_GATEWAY}:host-gateway")
    args+=(-p "${API_HOST_PORT}:${API_CONTAINER_PORT}")
  fi
  args+=(
    -v "${DATA_DIR}:/data:ro"
    -e "PORT=${API_CONTAINER_PORT}"
    -e "KTG_API_HOST=0.0.0.0"
    -e "KTG_PG_DSN=${PG_DSN}"
    -e "KTG_GEOIP_GATE_MODE=${KTG_GEOIP_GATE_MODE:-off}"
    -e "KTG_OPS_TABLE_STATS_CAPTURE_INTERVAL_MINUTES=${KTG_OPS_TABLE_STATS_CAPTURE_INTERVAL_MINUTES:-0}"
    -e "KTG_RUSTFS_ENABLED=${RUSTFS_ENABLED}"
    -e "KTG_RUSTFS_ENDPOINT_URL=${RUSTFS_ENDPOINT_URL}"
    -e "KTG_RUSTFS_BUCKET=${RUSTFS_BUCKET}"
    -e "KTG_RUSTFS_PREFIX=${RUSTFS_PREFIX}"
    -e "KTG_RUSTFS_REGION=${RUSTFS_REGION}"
    -e "KTG_RUSTFS_LOCAL_IMPORT_ROOTS=/data"
  )
  if [[ -n "$rustfs_access_key" ]]; then
    args+=(-e "KTG_RUSTFS_ACCESS_KEY=${rustfs_access_key}")
  fi
  if [[ -n "$rustfs_secret_key" ]]; then
    args+=(-e "KTG_RUSTFS_SECRET_KEY=${rustfs_secret_key}")
  fi
  if [[ -n "$vworld_key" ]]; then
    args+=(-e "KTG_VWORLD_API_KEY=${vworld_key}")
  fi
  args+=("$API_IMAGE")

  log "starting API container: $API_CONTAINER"
  docker "${args[@]}" >/dev/null
  log "API ready target: http://127.0.0.1:${API_HOST_PORT}"
}

run_ui() {
  require_docker
  ensure_network
  remove_container "$UI_CONTAINER"
  free_host_port "$UI_HOST_PORT"

  local vworld_key
  vworld_key="$(resolve_vworld_key)"
  local args=(run -d --name "$UI_CONTAINER" --restart "$RESTART_POLICY")
  if [[ "$NETWORK_MODE" == "host" ]]; then
    args+=(--network host)
  else
    args+=(--network "$NETWORK_NAME" --add-host "${HOST_GATEWAY}:host-gateway")
    args+=(-p "${UI_HOST_PORT}:${UI_CONTAINER_PORT}")
  fi
  args+=(
    -e "PORT=${UI_CONTAINER_PORT}"
    -e "HOSTNAME=0.0.0.0"
    -e "KTG_API_INTERNAL_URL=${UI_API_INTERNAL_URL}"
    -e "NEXT_PUBLIC_API_BASE_URL=/api/proxy"
  )
  if [[ -n "$vworld_key" ]]; then
    args+=(
      -e "KTG_VWORLD_API_KEY=${vworld_key}"
      -e "NEXT_PUBLIC_VWORLD_API_KEY=${vworld_key}"
    )
  else
    log "warning: VWorld key not found; UI will render coordinate fallback instead of map tiles"
  fi
  args+=("$UI_IMAGE")

  log "starting UI container: $UI_CONTAINER"
  docker "${args[@]}" >/dev/null
  log "UI ready target: http://127.0.0.1:${UI_HOST_PORT}/debug/geocode"
}

down() {
  require_docker
  remove_container "$UI_CONTAINER"
  remove_container "$API_CONTAINER"
}

status() {
  require_docker
  docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}' \
    | sed -n '1p;/kor-travel-geo-api-latest/p;/kor-travel-geo-ui-latest/p'
}

logs() {
  require_docker
  case "${1:-api}" in
    api) docker logs -f "$API_CONTAINER" ;;
    ui) docker logs -f "$UI_CONTAINER" ;;
    *) echo "usage: scripts/docker_app.sh logs [api|ui]" >&2; exit 2 ;;
  esac
}

run_cli() {
  require_docker
  ensure_network
  local vworld_key rustfs_access_key rustfs_secret_key
  vworld_key="$(resolve_vworld_key)"
  rustfs_access_key="$(resolve_env_or_dotenv KTG_RUSTFS_ACCESS_KEY "")"
  rustfs_secret_key="$(resolve_env_or_dotenv KTG_RUSTFS_SECRET_KEY "")"

  local args=(run --rm)
  if [[ "$NETWORK_MODE" == "host" ]]; then
    args+=(--network host)
  else
    args+=(--network "$NETWORK_NAME" --add-host "${HOST_GATEWAY}:host-gateway")
  fi
  args+=(
    -v "${DATA_DIR}:/data:ro"
    -e "KTG_PG_DSN=${PG_DSN}"
    -e "KTG_LOADER_DATA_DIR=/data"
    -e "KTG_GEOIP_GATE_MODE=${KTG_GEOIP_GATE_MODE:-off}"
    -e "KTG_OPS_TABLE_STATS_CAPTURE_INTERVAL_MINUTES=${KTG_OPS_TABLE_STATS_CAPTURE_INTERVAL_MINUTES:-0}"
    -e "KTG_RUSTFS_ENABLED=${RUSTFS_ENABLED}"
    -e "KTG_RUSTFS_ENDPOINT_URL=${RUSTFS_ENDPOINT_URL}"
    -e "KTG_RUSTFS_BUCKET=${RUSTFS_BUCKET}"
    -e "KTG_RUSTFS_PREFIX=${RUSTFS_PREFIX}"
    -e "KTG_RUSTFS_REGION=${RUSTFS_REGION}"
  )
  if [[ -n "$rustfs_access_key" ]]; then
    args+=(-e "KTG_RUSTFS_ACCESS_KEY=${rustfs_access_key}")
  fi
  if [[ -n "$rustfs_secret_key" ]]; then
    args+=(-e "KTG_RUSTFS_SECRET_KEY=${rustfs_secret_key}")
  fi
  if [[ -n "$vworld_key" ]]; then
    args+=(-e "KTG_VWORLD_API_KEY=${vworld_key}")
  fi
  args+=("$API_IMAGE" "$@")
  docker "${args[@]}"
}

load_full_set() {
  local args=(ktgctl load full-set /data)
  [[ -z "${JUSO_YYYYMM:-}" ]] || args+=(--juso-yyyymm "$JUSO_YYYYMM")
  [[ -z "${PARCEL_LINK_YYYYMM:-}" ]] || args+=(--parcel-link-yyyymm "$PARCEL_LINK_YYYYMM")
  [[ -z "${LOCSUM_YYYYMM:-}" ]] || args+=(--locsum-yyyymm "$LOCSUM_YYYYMM")
  [[ -z "${NAVI_YYYYMM:-}" ]] || args+=(--navi-yyyymm "$NAVI_YYYYMM")
  [[ -z "${SHP_YYYYMM:-}" ]] || args+=(--shp-yyyymm "$SHP_YYYYMM")
  [[ -z "${ROADADDR_ENTRANCE_YYYYMM:-}" ]] || args+=(--roadaddr-entrance-yyyymm "$ROADADDR_ENTRANCE_YYYYMM")
  [[ "${ALLOW_MIXED_YYYYMM:-0}" != "1" ]] || args+=(--allow-mixed-yyyymm)
  [[ -z "${CONFIRM_SOURCE_SET:-}" ]] || args+=(--confirm-source-set "$CONFIRM_SOURCE_SET")
  [[ "${PLAN_ONLY:-0}" != "1" ]] || args+=(--plan-only)
  args+=("$@")
  run_cli "${args[@]}"
}

main() {
  local command="${1:-}"
  [[ -n "$command" ]] || { usage; exit 2; }
  shift || true

  case "$command" in
    build-api) build_api ;;
    build-ui) build_ui ;;
    build) build_api; build_ui ;;
    up-api) run_api ;;
    up-ui) run_ui ;;
    up) run_api; run_ui ;;
    down) down ;;
    status) status ;;
    logs) logs "$@" ;;
    cli) [[ $# -gt 0 ]] || { echo "cli requires a command" >&2; exit 2; }; run_cli "$@" ;;
    load) run_cli ktgctl load "$@" ;;
    load-full-set) load_full_set "$@" ;;
    help|-h|--help) usage ;;
    *) echo "unknown command: $command" >&2; usage; exit 2 ;;
  esac
}

main "$@"
