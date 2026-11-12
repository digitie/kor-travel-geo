#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
UI_DIR="$ROOT_DIR/kor-travel-geo-ui"

if ! command -v npm >/dev/null 2>&1; then
  echo "npm을 찾지 못했습니다. .nvmrc와 private package.json의 Linux Node/npm을 준비하세요." >&2
  exit 127
fi

NPM_PATH="$(command -v npm)"
case "$NPM_PATH" in
  /mnt/*|*.exe|*.cmd)
    cat >&2 <<EOF
Windows npm 경로를 거부합니다: $NPM_PATH
WSL/Linux Node/npm으로 실행하세요. Playwright는 N150 Linux에서 먼저 실행하고,
Windows fallback은 Linux 실행이 불가능할 때만 사유와 명령을 별도 기록합니다.
EOF
    exit 2
    ;;
esac

cd "$UI_DIR"

EXPECTED_NODE="$(cat "$ROOT_DIR/.nvmrc")"
EXPECTED_NPM="$(node -p 'require("./package.json").engines.npm')"
if [[ "$(node --version)" != "v$EXPECTED_NODE" || "$(npm --version)" != "$EXPECTED_NPM" ]]; then
  echo "Node $EXPECTED_NODE / npm $EXPECTED_NPM 을 선택한 뒤 다시 실행하세요." >&2
  exit 2
fi

if [[ "${1:-}" == "--install" ]]; then
  npm ci --engine-strict
fi

npm run gen:types
npm run check:dependencies
npm run doctor
npm run lint
npm run type-check
npm run test
npm run build
