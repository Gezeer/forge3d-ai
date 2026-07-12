#!/usr/bin/env bash
set -euo pipefail

HUNYUAN_URL="${FORGE3D_HUNYUAN_URL:-http://127.0.0.1:8080}"
FORGE3D_URL="${FORGE3D_TEST_API_URL:-http://127.0.0.1:8000}"

curl --fail --silent --show-error --max-time 5 "${HUNYUAN_URL}/" >/dev/null
echo "Hunyuan url=${HUNYUAN_URL} pids=$(pgrep -f 'Hunyuan|gradio' | tr '\n' ',' || true)"

curl --fail --silent --show-error --max-time 5 "${FORGE3D_URL}/health/live" >/dev/null
echo "Forge3D url=${FORGE3D_URL} pids=$(pgrep -f 'uvicorn.*main:app' | tr '\n' ',' || true)"
