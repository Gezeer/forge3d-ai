#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="${FORGE3D_ROOT:-/workspace/forge3d-ai}"
export PYTHONPATH="${ROOT_DIR}/backend${PYTHONPATH:+:${PYTHONPATH}}"
export FORGE3D_ENV="${FORGE3D_ENV:-production}"
export FORGE3D_UPLOAD_DIR="${FORGE3D_UPLOAD_DIR:-${ROOT_DIR}/uploads}"
export FORGE3D_OUTPUT_DIR="${FORGE3D_OUTPUT_DIR:-${ROOT_DIR}/outputs}"
export FORGE3D_JOBS_FILE="${FORGE3D_JOBS_FILE:-${FORGE3D_OUTPUT_DIR}/jobs.json}"
export FORGE3D_TRIPOSR_RUN="${FORGE3D_TRIPOSR_RUN:-/workspace/kai3d/models/TripoSR/run.py}"
export FORGE3D_TRIPOSR_PYTHON="${FORGE3D_TRIPOSR_PYTHON:-/workspace/kai3d/models/Hunyuan3D-2.1/venv/bin/python}"
export FORGE3D_TRIPOSR_DEVICE="${FORGE3D_TRIPOSR_DEVICE:-cuda:0}"
export FORGE3D_HUNYUAN_URL="${FORGE3D_HUNYUAN_URL:-http://127.0.0.1:8080}"

cd "${ROOT_DIR}/backend"
exec python3 -m uvicorn main:app --host 0.0.0.0 --port "${PORT:-8000}"
