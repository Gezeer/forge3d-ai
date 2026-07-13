#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="${FORGE3D_ROOT:-/workspace/forge3d-ai}"
WEB_DIR="${ROOT_DIR}/web"
PORT="${PORT:-3000}"
export FORGE3D_INTERNAL_API_URL="${FORGE3D_INTERNAL_API_URL:-http://127.0.0.1:8000}"

if ! command -v node >/dev/null 2>&1; then
  echo "Node.js is not available in PATH" >&2
  exit 2
fi
if ! command -v npm >/dev/null 2>&1; then
  echo "npm is not available in PATH" >&2
  exit 2
fi
if [[ ! -f "${WEB_DIR}/package-lock.json" ]]; then
  echo "Forge3D package-lock.json not found: ${WEB_DIR}" >&2
  exit 2
fi

cd "${WEB_DIR}"
if [[ ! -x node_modules/.bin/next ]]; then
  npm ci
fi
if [[ ! -f .next/BUILD_ID ]]; then
  npm run build
fi

echo "Forge3D web node=$(node --version) npm=$(npm --version) port=${PORT}"
exec npm run start -- --hostname 0.0.0.0 --port "${PORT}"
