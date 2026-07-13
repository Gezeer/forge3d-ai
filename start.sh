#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="${FORGE3D_ROOT:-/workspace/forge3d-ai}"
BACKEND_PORT="${PORT:-8000}"
FRONTEND_PORT="${FORGE3D_FRONTEND_PORT:-3000}"

cleanup() {
  local status=$?
  trap - EXIT INT TERM
  [[ -n "${API_PID:-}" ]] && kill "${API_PID}" 2>/dev/null || true
  [[ -n "${WEB_PID:-}" ]] && kill "${WEB_PID}" 2>/dev/null || true
  wait 2>/dev/null || true
  exit "${status}"
}
trap cleanup EXIT INT TERM

FORGE3D_ROOT="${ROOT_DIR}" PORT="${BACKEND_PORT}" \
  "${ROOT_DIR}/backend/scripts/start_runpod.sh" &
API_PID=$!

for _ in {1..30}; do
  if curl --fail --silent --max-time 2 \
    "http://127.0.0.1:${BACKEND_PORT}/health/live" >/dev/null; then
    break
  fi
  if ! kill -0 "${API_PID}" 2>/dev/null; then
    echo "Forge3D backend terminated during startup" >&2
    exit 1
  fi
  sleep 1
done
curl --fail --silent --show-error --max-time 5 \
  "http://127.0.0.1:${BACKEND_PORT}/health/live" >/dev/null

FORGE3D_ROOT="${ROOT_DIR}" \
FORGE3D_INTERNAL_API_URL="http://127.0.0.1:${BACKEND_PORT}" \
PORT="${FRONTEND_PORT}" \
  "${ROOT_DIR}/backend/scripts/start_web_runpod.sh" &
WEB_PID=$!

echo "Forge3D backend=http://0.0.0.0:${BACKEND_PORT} pid=${API_PID}"
echo "Forge3D frontend=http://0.0.0.0:${FRONTEND_PORT} pid=${WEB_PID}"

wait -n "${API_PID}" "${WEB_PID}"
