#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
export PYTHONPATH="${ROOT_DIR}/backend${PYTHONPATH:+:${PYTHONPATH}}"
export FORGE3D_ENV="${FORGE3D_ENV:-development}"
export FORGE3D_UPLOAD_DIR="${FORGE3D_UPLOAD_DIR:-${ROOT_DIR}/.runtime/uploads}"
export FORGE3D_OUTPUT_DIR="${FORGE3D_OUTPUT_DIR:-${ROOT_DIR}/.runtime/outputs}"
export FORGE3D_JOBS_FILE="${FORGE3D_JOBS_FILE:-${FORGE3D_OUTPUT_DIR}/jobs.json}"
export FORGE3D_CORS_ORIGINS="${FORGE3D_CORS_ORIGINS:-http://localhost:3000}"

exec "${ROOT_DIR}/.venv/bin/python" -m uvicorn main:app \
  --app-dir "${ROOT_DIR}/backend" --host 127.0.0.1 --port "${PORT:-8000}" --reload
