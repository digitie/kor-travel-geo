#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
UI_DIR="$ROOT_DIR/kor-travel-geo-ui"

API_IMAGE="${KTG_API_IMAGE:-kor-travel-geo-api:latest-main-gdal}"
UI_IMAGE="${KTG_UI_IMAGE:-kor-travel-geo-ui:latest-main}"
API_CONTAINER="${KTG_API_CONTAINER:-kor-travel-geo-api-latest}"
UI_CONTAINER="${KTG_UI_CONTAINER:-kor-travel-geo-ui-latest}"
RESTART_POLICY="${KTG_DOCKER_RESTART_POLICY:-unless-stopped}"
# 별도 지시가 없으면 dev 환경이 기본이다. dev는 host 네트워크 모드로 띄워 API/UI/DB/RustFS가
# 모두 루프백 127.0.0.1로 일관 동작한다(앱 포트는 12xxx — API 12501 / UI 12505).
# prod는 이 스크립트가 아니라 kor-travel-docker-manager로 올리고 공식 도메인을 쓴다(.env.prod).
# Docker Desktop(Windows/Mac) host 네트워크 제약이 있으면 KTG_DOCKER_NETWORK_MODE=bridge로 바꾼다.
NETWORK_MODE="${KTG_DOCKER_NETWORK_MODE:-host}"
NETWORK_NAME="${KTG_DOCKER_NETWORK:-kor-travel-geo-net}"
HOST_GATEWAY="${KTG_DOCKER_HOST_GATEWAY:-host.docker.internal}"

API_HOST_PORT="${KTG_API_PORT:-12501}"
API_CONTAINER_PORT="${KTG_API_CONTAINER_PORT:-12501}"
UI_HOST_PORT="${KTG_UI_PORT:-12505}"
UI_CONTAINER_PORT="${KTG_UI_CONTAINER_PORT:-12505}"
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

This script starts the kor-travel-geo API/UI containers for the DEV environment.
별도 지시가 없으면 dev 기본: host 네트워크 모드 + 루프백 127.0.0.1 + 앱 포트 12xxx
(API http://127.0.0.1:12501, UI http://127.0.0.1:12505). PostgreSQL/RustFS는 직접
구동하지 않고 127.0.0.1에 게시된(예: kor-travel-docker-manager) 인프라에 접속한다.
prod는 이 스크립트가 아니라 kor-travel-docker-manager로 올리고 공식 도메인을 쓴다.

이미 같은 컨테이너/포트가 떠 있으면 새 포트로 우회하지 않는다. 강제종료 여부를 물은 뒤,
거부하면(또는 비대화형에서 KTG_FORCE_KILL 미설정이면) 작업을 중지한다.
KTG_FORCE_KILL=1 이면 묻지 않고 강제종료 후 재기동한다.

Env files (KTG_ENV_FILE 우선 → .env → kor-travel-geo-ui/.env.local):
  KTG_ENV_FILE=.env.dev    # repo root 기준 dev 프로파일 — .env.dev.example 참고
  KTG_ENV_FILE=.env.prod   # repo root 기준 prod 프로파일 — .env.prod.example 참고

Important env:
  KTG_DOCKER_NETWORK_MODE=host                 # dev 기본. Docker Desktop 제약 시 bridge
  KTG_DOCKER_PG_DSN=postgresql+psycopg://addr:addr@127.0.0.1:5432/kor_travel_geo
  KTG_RUSTFS_ENABLED=1
  KTG_RUSTFS_ENDPOINT_URL=http://127.0.0.1:12101
  KTG_RUSTFS_BUCKET=kor-travel-geo
  KTG_RUSTFS_PREFIX=kor-travel-geo
  KTG_RUSTFS_ACCESS_KEY=<access key>
  KTG_RUSTFS_SECRET_KEY=<secret key>
  KTG_ADMIN_TRUSTED_PROXY_CIDRS=127.0.0.1/32,::1/128
  KTG_ADMIN_PROXY_SECRET=<shared admin proxy secret>
  KTG_UI_ADMIN_USERNAME=admin
  KTG_UI_ADMIN_PASSWORD_HASH=<pbkdf2 hash>
  KTG_UI_SESSION_SECRET=<random session secret>
  KTG_DOCKER_DATA_DIR=/mnt/f/dev/kor-travel-geo/data
  KTG_DOCKER_RESTART_POLICY=unless-stopped     # set to "no" to disable
  KTG_VWORLD_API_KEY=<runtime key>
  KTG_FORCE_KILL=1                             # 이미 떠 있어도 묻지 않고 강제종료
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
  local env_files=()
  if [[ -n "${KTG_ENV_FILE:-}" ]]; then
    if [[ "$KTG_ENV_FILE" == /* ]]; then
      env_files+=("$KTG_ENV_FILE")
    else
      env_files+=("$ROOT_DIR/$KTG_ENV_FILE")
    fi
  fi
  env_files+=("$ROOT_DIR/.env" "$UI_DIR/.env.local")
  for file in "${env_files[@]}"; do
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

# Re-resolve runtime config from process env > dotenv files > defaults. dotenv
# files are $KTG_ENV_FILE (e.g. .env.prod), $ROOT_DIR/.env, $UI_DIR/.env.local.
# Called inside run_* so a consolidated prod env file drives the URL/RustFS/CORS
# values, not just the process environment (top-level assigns read process env
# only). This is what makes `KTG_ENV_FILE=.env.prod scripts/docker_app.sh up`
# pick up the prod API/RustFS domains and CORS origins.
resolve_runtime_env() {
  PG_DSN="$(resolve_env_or_dotenv KTG_DOCKER_PG_DSN "$(resolve_env_or_dotenv KTG_PG_DSN "$DEFAULT_PG_DSN")")"
  UI_API_INTERNAL_URL="$(resolve_env_or_dotenv KTG_API_INTERNAL_URL "$DEFAULT_UI_API_URL")"
  RUSTFS_ENABLED="$(resolve_env_or_dotenv KTG_RUSTFS_ENABLED "0")"
  RUSTFS_ENDPOINT_URL="$(resolve_env_or_dotenv KTG_RUSTFS_ENDPOINT_URL "$DEFAULT_RUSTFS_ENDPOINT")"
  RUSTFS_BUCKET="$(resolve_env_or_dotenv KTG_RUSTFS_BUCKET "kor-travel-geo")"
  RUSTFS_PREFIX="$(resolve_env_or_dotenv KTG_RUSTFS_PREFIX "kor-travel-geo")"
  RUSTFS_REGION="$(resolve_env_or_dotenv KTG_RUSTFS_REGION "us-east-1")"
  API_CORS_ORIGINS="$(resolve_env_or_dotenv KTG_API_CORS_ORIGINS "[]")"
  GEOIP_GATE_MODE="$(resolve_env_or_dotenv KTG_GEOIP_GATE_MODE "off")"
  ADMIN_TRUSTED_PROXY_CIDRS="$(resolve_env_or_dotenv KTG_ADMIN_TRUSTED_PROXY_CIDRS "")"
  ADMIN_PROXY_SECRET="$(resolve_env_or_dotenv KTG_ADMIN_PROXY_SECRET "")"
  UI_ADMIN_USERNAME="$(resolve_env_or_dotenv KTG_UI_ADMIN_USERNAME "admin")"
  UI_ADMIN_PASSWORD_HASH="$(resolve_env_or_dotenv KTG_UI_ADMIN_PASSWORD_HASH "")"
  UI_SESSION_SECRET="$(resolve_env_or_dotenv KTG_UI_SESSION_SECRET "")"
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

# 이미 떠 있는 컨테이너/포트를 강제종료할지 사용자에게 확인한다.
# 정책(prod 유무 무관): 새 포트로 우회하지 않는다. 거부하면 작업을 중지한다(컨테이너를 띄우지 않음).
#  - KTG_FORCE_KILL=1|true|yes → 묻지 않고 강제종료(자동화용)
#  - 비대화형(TTY 없음) + KTG_FORCE_KILL 미설정 → 안전하게 중지(exit 3)
#  - 대화형 → [y/N] 프롬프트. 기본 No → 중지
confirm_force_kill() {
  local target="$1" reasons="$2"
  case "${KTG_FORCE_KILL:-}" in
    1 | true | TRUE | yes | YES)
      log "KTG_FORCE_KILL set — 강제종료 후 재기동: ${target} (${reasons})"
      return 0
      ;;
  esac
  if [[ ! -t 0 ]]; then
    log "ERROR: ${target} 가(이) 이미 사용 중입니다 (${reasons})."
    log "비대화형 환경에서는 강제종료하지 않습니다. 새 포트로 열지 않고 작업을 중지합니다."
    log "강제 교체가 필요하면 KTG_FORCE_KILL=1 로 다시 실행하세요."
    exit 3
  fi
  local reply=""
  printf '[docker-app] %s 가(이) 이미 사용 중입니다 (%s).\n' "$target" "$reasons" >&2
  printf '[docker-app] 강제종료하고 다시 띄울까요? [y/N] ' >&2
  read -r reply || reply=""
  case "$reply" in
    y | Y | yes | YES)
      return 0
      ;;
    *)
      log "사용자가 강제종료를 거부했습니다. 새 포트로 열지 않고 작업을 중지합니다."
      exit 3
      ;;
  esac
}

# dev 포트/컨테이너가 이미 사용 중인지 검사하고, 그렇다면 confirm_force_kill로 확인한다.
# 동의(또는 KTG_FORCE_KILL)한 경우에만 호출부의 remove_container/free_host_port가 정리한다.
guard_running() {
  local name="$1" port="$2"
  local reasons=()
  if docker ps -a --format '{{.Names}}' 2>/dev/null | grep -Fxq "$name"; then
    reasons+=("container '${name}'")
  fi
  local published
  published="$(docker ps --filter "publish=${port}" --format '{{.Names}}' 2>/dev/null | paste -sd' ' - || true)"
  [[ -n "$published" ]] && reasons+=("docker publish :${port} (${published})")
  local pids=""
  if command -v lsof >/dev/null 2>&1; then
    pids="$(lsof -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null | paste -sd' ' - || true)"
  elif command -v fuser >/dev/null 2>&1; then
    pids="$(fuser -n tcp "$port" 2>/dev/null | tr -s ' ' || true)"
  fi
  [[ -n "$pids" ]] && reasons+=("host PID :${port} (${pids})")
  if [[ ${#reasons[@]} -gt 0 ]]; then
    local joined
    printf -v joined '%s; ' "${reasons[@]}"
    confirm_force_kill "${name}:${port}" "${joined%; }"
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
  guard_running "$API_CONTAINER" "$API_HOST_PORT"
  remove_container "$API_CONTAINER"
  free_host_port "$API_HOST_PORT"
  resolve_runtime_env

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
    -e "KTG_GEOIP_GATE_MODE=${GEOIP_GATE_MODE}"
    -e "KTG_API_CORS_ORIGINS=${API_CORS_ORIGINS}"
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
  if [[ -n "$ADMIN_TRUSTED_PROXY_CIDRS" ]]; then
    args+=(-e "KTG_ADMIN_TRUSTED_PROXY_CIDRS=${ADMIN_TRUSTED_PROXY_CIDRS}")
  fi
  if [[ -n "$ADMIN_PROXY_SECRET" ]]; then
    args+=(-e "KTG_ADMIN_PROXY_SECRET=${ADMIN_PROXY_SECRET}")
  fi
  args+=("$API_IMAGE")

  log "starting API container: $API_CONTAINER"
  docker "${args[@]}" >/dev/null
  log "API ready target: http://127.0.0.1:${API_HOST_PORT}"
}

run_ui() {
  require_docker
  ensure_network
  guard_running "$UI_CONTAINER" "$UI_HOST_PORT"
  remove_container "$UI_CONTAINER"
  free_host_port "$UI_HOST_PORT"
  resolve_runtime_env

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
    -e "KTG_UI_ADMIN_USERNAME=${UI_ADMIN_USERNAME}"
  )
  if [[ -n "$UI_ADMIN_PASSWORD_HASH" ]]; then
    args+=(-e "KTG_UI_ADMIN_PASSWORD_HASH=${UI_ADMIN_PASSWORD_HASH}")
  fi
  if [[ -n "$UI_SESSION_SECRET" ]]; then
    args+=(-e "KTG_UI_SESSION_SECRET=${UI_SESSION_SECRET}")
  fi
  if [[ -n "$ADMIN_PROXY_SECRET" ]]; then
    args+=(-e "KTG_ADMIN_PROXY_SECRET=${ADMIN_PROXY_SECRET}")
  fi
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
  resolve_runtime_env
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
    -e "KTG_GEOIP_GATE_MODE=${GEOIP_GATE_MODE}"
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
    help|-h|--help) usage ;;
    *) echo "unknown command: $command" >&2; usage; exit 2 ;;
  esac
}

main "$@"
