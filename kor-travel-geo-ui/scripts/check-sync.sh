#!/usr/bin/env bash
set -euo pipefail
npm run gen:types
git diff --exit-code -- types/api.gen.ts lib/schemas.gen.ts
