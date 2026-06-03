#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
UI_DIR="$ROOT_DIR/kraddr-geo-ui"

API_IMAGE="${KRADDR_GEO_API_IMAGE:-kraddr-geo-api:latest-main-gdal}"
UI_IMAGE="${KRADDR_GEO_UI_IMAGE:-kraddr-geo-ui:latest-main}"
RUSTFS_IMAGE="${KRADDR_GEO_RUSTFS_IMAGE:-rustfs/rustfs:latest}"
API_CONTAINER="${KRADDR_GEO_API_CONTAINER:-kraddr-geo-api-latest}"
UI_CONTAINER="${KRADDR_GEO_UI_CONTAINER:-kraddr-geo-ui-latest}"
RUSTFS_CONTAINER="${KRADDR_GEO_RUSTFS_CONTAINER:-kraddr-geo-rustfs}"
NETWORK_MODE="${KRADDR_GEO_DOCKER_NETWORK_MODE:-bridge}"
NETWORK_NAME="${KRADDR_GEO_DOCKER_NETWORK:-kraddr-geo-net}"
HOST_GATEWAY="${KRADDR_GEO_DOCKER_HOST_GATEWAY:-host.docker.internal}"

API_HOST_PORT="${KRADDR_GEO_API_PORT:-9001}"
API_CONTAINER_PORT="${KRADDR_GEO_API_CONTAINER_PORT:-9001}"
UI_HOST_PORT="${KRADDR_GEO_UI_PORT:-9002}"
UI_CONTAINER_PORT="${KRADDR_GEO_UI_CONTAINER_PORT:-9002}"
RUSTFS_HOST_PORT="${KRADDR_GEO_RUSTFS_PORT:-9003}"
RUSTFS_CONTAINER_PORT="${KRADDR_GEO_RUSTFS_CONTAINER_PORT:-9003}"
RUSTFS_CONSOLE_HOST_PORT="${KRADDR_GEO_RUSTFS_CONSOLE_PORT:-9004}"
RUSTFS_CONSOLE_CONTAINER_PORT="${KRADDR_GEO_RUSTFS_CONSOLE_CONTAINER_PORT:-9004}"
DB_PORT="${KRADDR_GEO_DB_PORT:-15434}"
DATA_DIR="${KRADDR_GEO_DOCKER_DATA_DIR:-${DATA_DIR:-/mnt/f/dev/python-kraddr-geo/data}}"
RUSTFS_DATA_DIR="${KRADDR_GEO_RUSTFS_DATA_DIR:-$HOME/kraddr-geo-data/rustfs}"
RUSTFS_BUCKET="${KRADDR_GEO_RUSTFS_BUCKET:-kraddr-geo}"
RUSTFS_PREFIX="${KRADDR_GEO_RUSTFS_PREFIX:-python-kraddr-geo}"
RUSTFS_REUSE_EXISTING="${KRADDR_GEO_RUSTFS_REUSE_EXISTING:-0}"

if [[ "$NETWORK_MODE" == "host" ]]; then
  DEFAULT_PG_HOST="127.0.0.1"
  DEFAULT_UI_API_URL="http://127.0.0.1:${API_CONTAINER_PORT}"
  DEFAULT_RUSTFS_ENDPOINT="http://127.0.0.1:${RUSTFS_CONTAINER_PORT}"
else
  DEFAULT_PG_HOST="$HOST_GATEWAY"
  DEFAULT_UI_API_URL="http://kraddr-geo-api:${API_CONTAINER_PORT}"
  DEFAULT_RUSTFS_ENDPOINT="http://kraddr-geo-rustfs:${RUSTFS_CONTAINER_PORT}"
fi

DEFAULT_PG_DSN="postgresql+psycopg://addr:addr@${DEFAULT_PG_HOST}:${DB_PORT}/kraddr_geo"
PG_DSN="${KRADDR_GEO_DOCKER_PG_DSN:-${KRADDR_GEO_PG_DSN:-$DEFAULT_PG_DSN}}"
UI_API_INTERNAL_URL="${KRADDR_GEO_API_INTERNAL_URL:-$DEFAULT_UI_API_URL}"
RUSTFS_ENDPOINT_URL="${KRADDR_GEO_RUSTFS_ENDPOINT_URL:-$DEFAULT_RUSTFS_ENDPOINT}"

usage() {
  cat <<'EOF'
Usage:
  scripts/docker_app.sh build-api
  scripts/docker_app.sh build-ui
  scripts/docker_app.sh build
  scripts/docker_app.sh up-rustfs
  scripts/docker_app.sh up-api
  scripts/docker_app.sh up-ui
  scripts/docker_app.sh up
  scripts/docker_app.sh down-rustfs
  scripts/docker_app.sh down
  scripts/docker_app.sh status
  scripts/docker_app.sh logs [api|ui|rustfs]
  scripts/docker_app.sh cli <command> [args...]
  scripts/docker_app.sh load <kraddr-geo load args...>
  scripts/docker_app.sh load-full-set [extra kraddr-geo load full-set args...]

Defaults:
  API image/container: kraddr-geo-api:latest-main-gdal / kraddr-geo-api-latest
  UI image/container:  kraddr-geo-ui:latest-main / kraddr-geo-ui-latest
  RustFS container:    kraddr-geo-rustfs
  Network:             bridge network kraddr-geo-net
  API URL:             http://127.0.0.1:9001
  UI URL:              http://127.0.0.1:9002
  RustFS S3 URL:       http://127.0.0.1:9003
  RustFS console URL:  http://127.0.0.1:9004

Important env overrides:
  KRADDR_GEO_DOCKER_NETWORK_MODE=bridge|host
  KRADDR_GEO_DOCKER_PG_DSN=postgresql+psycopg://addr:addr@host.docker.internal:15434/kraddr_geo
  KRADDR_GEO_DOCKER_DATA_DIR=/mnt/f/dev/python-kraddr-geo/data
  KRADDR_GEO_VWORLD_API_KEY=<runtime key>
  KRADDR_GEO_RUSTFS_ACCESS_KEY=<rustfs access key>
  KRADDR_GEO_RUSTFS_SECRET_KEY=<rustfs secret key>
  KRADDR_GEO_RUSTFS_DATA_DIR=$HOME/kraddr-geo-data/rustfs
  KRADDR_GEO_RUSTFS_REUSE_EXISTING=1   # opt-in: reuse another RustFS already publishing 9003

VWorld key resolution:
  1. KRADDR_GEO_VWORLD_API_KEY process env
  2. KRADDR_GEO_VWORLD_API_KEY in .env
  3. NEXT_PUBLIC_VWORLD_API_KEY process env
  4. NEXT_PUBLIC_VWORLD_API_KEY in .env or kraddr-geo-ui/.env.local

Examples:
  scripts/docker_app.sh build
  scripts/docker_app.sh up
  scripts/docker_app.sh load juso "/data/juso/202603_도로명주소 한글_전체분" --yyyymm 202603
  PLAN_ONLY=1 scripts/docker_app.sh load-full-set --allow-mixed-yyyymm
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
  if [[ -n "${KRADDR_GEO_VWORLD_API_KEY:-}" ]]; then
    printf '%s' "$KRADDR_GEO_VWORLD_API_KEY"
    return 0
  fi
  if dotenv_get KRADDR_GEO_VWORLD_API_KEY; then
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

container_publishing_port() {
  local port="$1"
  docker ps --format '{{.Names}}\t{{.Ports}}' \
    | awk -v port="$port" '
      $0 ~ ":" port "->" || $0 ~ ":" port "-" {
        print $1
        exit
      }
    '
}

container_env_get() {
  local container="$1"
  local key="$2"
  [[ -n "$container" ]] || return 1
  docker inspect "$container" --format '{{range .Config.Env}}{{println .}}{{end}}' 2>/dev/null \
    | sed -n "s/^${key}=//p" \
    | tail -n 1
}

container_label_get() {
  local container="$1"
  local key="$2"
  [[ -n "$container" ]] || return 1
  docker inspect "$container" --format "{{ index .Config.Labels \"$key\" }}" 2>/dev/null || true
}

current_rustfs_container() {
  if docker ps --format '{{.Names}}' | grep -Fxq "$RUSTFS_CONTAINER"; then
    printf '%s' "$RUSTFS_CONTAINER"
    return 0
  fi
  container_publishing_port "$RUSTFS_HOST_PORT"
}

resolve_rustfs_env() {
  local key="$1"
  local default_value="$2"
  local current_value="${!key:-}"
  local container value container_key
  if [[ -n "$current_value" ]]; then
    printf '%s' "$current_value"
    return 0
  fi
  if dotenv_get "$key"; then
    return 0
  fi
  container="$(current_rustfs_container)"
  value="$(container_env_get "$container" "$key" || true)"
  if [[ -z "$value" && "$key" == KRADDR_GEO_RUSTFS_* ]]; then
    container_key="${key#KRADDR_GEO_}"
    value="$(container_env_get "$container" "$container_key" || true)"
  fi
  if [[ -n "$value" ]]; then
    printf '%s' "$value"
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

ensure_rustfs_network_alias() {
  local container="$1"
  [[ "$NETWORK_MODE" != "host" ]] || return 0
  ensure_network
  if docker inspect "$container" --format '{{json .NetworkSettings.Networks}}' \
    | grep -q "\"${NETWORK_NAME}\""; then
    return 0
  fi
  log "connecting existing RustFS container to $NETWORK_NAME as kraddr-geo-rustfs: $container"
  docker network connect --alias kraddr-geo-rustfs "$NETWORK_NAME" "$container"
}

stop_compose_owner() {
  local container="$1"
  local project service config_files config_file
  project="$(container_label_get "$container" com.docker.compose.project)"
  service="$(container_label_get "$container" com.docker.compose.service)"
  config_files="$(container_label_get "$container" com.docker.compose.project.config_files)"
  [[ -n "$project" && -n "$service" && -n "$config_files" ]] || return 0

  config_file="${config_files%%,*}"
  [[ -f "$config_file" ]] || return 0
  log "stopping non-managed RustFS compose service before removal: project=$project service=$service"
  docker compose -p "$project" -f "$config_file" stop "$service" >/dev/null || true
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

run_rustfs() {
  require_docker
  ensure_network
  local existing
  existing="$(container_publishing_port "$RUSTFS_HOST_PORT")"
  if [[ -n "$existing" && "$existing" != "$RUSTFS_CONTAINER" ]]; then
    if [[ "$RUSTFS_REUSE_EXISTING" == "1" ]]; then
      log "using existing RustFS container on host port ${RUSTFS_HOST_PORT}: $existing"
      ensure_rustfs_network_alias "$existing"
      return 0
    fi
    log "removing non-managed RustFS container on host port ${RUSTFS_HOST_PORT}: $existing"
    stop_compose_owner "$existing"
    docker rm -f "$existing" >/dev/null
  fi
  remove_container "$RUSTFS_CONTAINER"
  if [[ "$NETWORK_MODE" != "host" ]]; then
    free_host_port "$RUSTFS_HOST_PORT"
    free_host_port "$RUSTFS_CONSOLE_HOST_PORT"
  fi

  local access_key secret_key
  access_key="$(resolve_rustfs_env KRADDR_GEO_RUSTFS_ACCESS_KEY rustfsadmin)"
  secret_key="$(resolve_rustfs_env KRADDR_GEO_RUSTFS_SECRET_KEY rustfsadmin)"
  mkdir -p "$RUSTFS_DATA_DIR"
  if command -v chown >/dev/null 2>&1; then
    chown 10001:10001 "$RUSTFS_DATA_DIR" 2>/dev/null || true
  fi
  chmod 0777 "$RUSTFS_DATA_DIR" 2>/dev/null || true

  local args=(run -d --name "$RUSTFS_CONTAINER")
  if [[ "$NETWORK_MODE" == "host" ]]; then
    args+=(--network host)
  else
    args+=(--network "$NETWORK_NAME" --network-alias kraddr-geo-rustfs)
    args+=(
      -p "${RUSTFS_HOST_PORT}:${RUSTFS_CONTAINER_PORT}"
      -p "${RUSTFS_CONSOLE_HOST_PORT}:${RUSTFS_CONSOLE_CONTAINER_PORT}"
    )
  fi
  args+=(
    -v "${RUSTFS_DATA_DIR}:/data"
    -e "RUSTFS_ACCESS_KEY=${access_key}"
    -e "RUSTFS_SECRET_KEY=${secret_key}"
    -e "RUSTFS_ADDRESS=:${RUSTFS_CONTAINER_PORT}"
    -e "RUSTFS_CONSOLE_ENABLE=true"
    -e "RUSTFS_CONSOLE_ADDRESS=:${RUSTFS_CONSOLE_CONTAINER_PORT}"
    "$RUSTFS_IMAGE"
    /data
  )

  log "starting RustFS container: $RUSTFS_CONTAINER"
  docker "${args[@]}" >/dev/null
  sleep 1
  if [[ "$(docker inspect "$RUSTFS_CONTAINER" --format '{{.State.Running}}' 2>/dev/null)" != "true" ]]; then
    docker logs "$RUSTFS_CONTAINER" --tail 80 2>/dev/null || true
    return 1
  fi
  log "RustFS S3 ready target: http://127.0.0.1:${RUSTFS_HOST_PORT}"
  log "RustFS console target: http://127.0.0.1:${RUSTFS_CONSOLE_HOST_PORT}"
}

docker_network_args() {
  if [[ "$NETWORK_MODE" == "host" ]]; then
    printf '%s\n' --network host
    return 0
  fi
  printf '%s\n' --network "$NETWORK_NAME" --add-host "${HOST_GATEWAY}:host-gateway"
}

run_api() {
  require_docker
  ensure_network
  remove_container "$API_CONTAINER"
  free_host_port "$API_HOST_PORT"

  local vworld_key
  vworld_key="$(resolve_vworld_key)"
  local rustfs_access_key rustfs_secret_key
  rustfs_access_key="$(resolve_rustfs_env KRADDR_GEO_RUSTFS_ACCESS_KEY rustfsadmin)"
  rustfs_secret_key="$(resolve_rustfs_env KRADDR_GEO_RUSTFS_SECRET_KEY rustfsadmin)"
  local args=(run -d --name "$API_CONTAINER")
  if [[ "$NETWORK_MODE" == "host" ]]; then
    args+=(--network host)
  else
    args+=(--network "$NETWORK_NAME" --network-alias kraddr-geo-api --add-host "${HOST_GATEWAY}:host-gateway")
    args+=(-p "${API_HOST_PORT}:${API_CONTAINER_PORT}")
  fi
  args+=(
    -v "${DATA_DIR}:/data:ro"
    -e "PORT=${API_CONTAINER_PORT}"
    -e "KRADDR_GEO_API_HOST=0.0.0.0"
    -e "KRADDR_GEO_PG_DSN=${PG_DSN}"
    -e "KRADDR_GEO_GEOIP_GATE_MODE=${KRADDR_GEO_GEOIP_GATE_MODE:-off}"
    -e "KRADDR_GEO_OPS_TABLE_STATS_CAPTURE_INTERVAL_MINUTES=${KRADDR_GEO_OPS_TABLE_STATS_CAPTURE_INTERVAL_MINUTES:-0}"
    -e "KRADDR_GEO_RUSTFS_ENABLED=${KRADDR_GEO_RUSTFS_ENABLED:-1}"
    -e "KRADDR_GEO_RUSTFS_ENDPOINT_URL=${RUSTFS_ENDPOINT_URL}"
    -e "KRADDR_GEO_RUSTFS_BUCKET=${RUSTFS_BUCKET}"
    -e "KRADDR_GEO_RUSTFS_PREFIX=${RUSTFS_PREFIX}"
    -e "KRADDR_GEO_RUSTFS_ACCESS_KEY=${rustfs_access_key}"
    -e "KRADDR_GEO_RUSTFS_SECRET_KEY=${rustfs_secret_key}"
    -e "KRADDR_GEO_RUSTFS_LOCAL_IMPORT_ROOTS=/data"
  )
  if [[ -n "$vworld_key" ]]; then
    args+=(-e "KRADDR_GEO_VWORLD_API_KEY=${vworld_key}")
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
  local args=(run -d --name "$UI_CONTAINER")
  if [[ "$NETWORK_MODE" == "host" ]]; then
    args+=(--network host)
  else
    args+=(--network "$NETWORK_NAME" --add-host "${HOST_GATEWAY}:host-gateway")
    args+=(-p "${UI_HOST_PORT}:${UI_CONTAINER_PORT}")
  fi
  args+=(
    -e "PORT=${UI_CONTAINER_PORT}"
    -e "HOSTNAME=0.0.0.0"
    -e "KRADDR_GEO_API_INTERNAL_URL=${UI_API_INTERNAL_URL}"
    -e "NEXT_PUBLIC_API_BASE_URL=/api/proxy"
  )
  if [[ -n "$vworld_key" ]]; then
    args+=(
      -e "KRADDR_GEO_VWORLD_API_KEY=${vworld_key}"
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

down_rustfs() {
  require_docker
  remove_container "$RUSTFS_CONTAINER"
}

status() {
  require_docker
  docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}' \
    | sed -n '1p;/kraddr-geo-api-latest/p;/kraddr-geo-ui-latest/p;/kraddr-geo-rustfs/p;/kraddr-geo-t027-final/p'
}

logs() {
  require_docker
  case "${1:-api}" in
    api) docker logs -f "$API_CONTAINER" ;;
    ui) docker logs -f "$UI_CONTAINER" ;;
    rustfs) docker logs -f "$RUSTFS_CONTAINER" ;;
    *) echo "usage: scripts/docker_app.sh logs [api|ui|rustfs]" >&2; exit 2 ;;
  esac
}

run_cli() {
  require_docker
  ensure_network
  local vworld_key
  vworld_key="$(resolve_vworld_key)"
  local args=(run --rm)
  if [[ "$NETWORK_MODE" == "host" ]]; then
    args+=(--network host)
  else
    args+=(--network "$NETWORK_NAME" --add-host "${HOST_GATEWAY}:host-gateway")
  fi
  args+=(
    -v "${DATA_DIR}:/data:ro"
    -e "KRADDR_GEO_PG_DSN=${PG_DSN}"
    -e "KRADDR_GEO_LOADER_DATA_DIR=/data"
    -e "KRADDR_GEO_GEOIP_GATE_MODE=${KRADDR_GEO_GEOIP_GATE_MODE:-off}"
    -e "KRADDR_GEO_OPS_TABLE_STATS_CAPTURE_INTERVAL_MINUTES=${KRADDR_GEO_OPS_TABLE_STATS_CAPTURE_INTERVAL_MINUTES:-0}"
  )
  if [[ -n "$vworld_key" ]]; then
    args+=(-e "KRADDR_GEO_VWORLD_API_KEY=${vworld_key}")
  fi
  args+=("$API_IMAGE" "$@")
  docker "${args[@]}"
}

load_full_set() {
  local args=(kraddr-geo load full-set /data)
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
    up-rustfs) run_rustfs ;;
    up-api) run_api ;;
    up-ui) run_ui ;;
    up) run_rustfs; run_api; run_ui ;;
    down-rustfs) down_rustfs ;;
    down) down ;;
    status) status ;;
    logs) logs "$@" ;;
    cli) [[ $# -gt 0 ]] || { echo "cli requires a command" >&2; exit 2; }; run_cli "$@" ;;
    load) run_cli kraddr-geo load "$@" ;;
    load-full-set) load_full_set "$@" ;;
    help|-h|--help) usage ;;
    *) echo "unknown command: $command" >&2; usage; exit 2 ;;
  esac
}

main "$@"
