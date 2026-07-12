#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="${FORGE3D_ROOT:-/workspace/forge3d-ai}"
export RUN_TEXTURE_GPU_TESTS=1
export FORGE3D_TEST_API_URL="${FORGE3D_TEST_API_URL:-http://127.0.0.1:8000}"
if [[ -z "${FORGE3D_TEXTURE_TEST_JOB_ID:-}" ]]; then echo "Defina FORGE3D_TEXTURE_TEST_JOB_ID para um shape completed." >&2; exit 1; fi
cd "${ROOT_DIR}"
PYTHONPATH=backend python3 -m pytest -m texture_gpu -vv --tb=short
