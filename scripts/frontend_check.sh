#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
UI_DIR="$ROOT_DIR/kraddr-geo-ui"

if ! command -v npm >/dev/null 2>&1; then
  echo "npm not found. Install Linux Node/npm in WSL before running frontend checks." >&2
  exit 127
fi

NPM_PATH="$(command -v npm)"
case "$NPM_PATH" in
  /mnt/*|*.exe|*.cmd)
    cat >&2 <<EOF
Windows npm detected: $NPM_PATH
Run this script with Linux Node/npm in WSL. For browser rendering and Playwright,
use the Windows Node/browser environment and record the Windows command separately.
EOF
    exit 2
    ;;
esac

cd "$UI_DIR"

if [[ "${1:-}" == "--install" ]]; then
  npm ci
fi

npm run gen:types
npm run lint
npm run type-check
npm run test
npm run build
