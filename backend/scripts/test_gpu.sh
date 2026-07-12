#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="${FORGE3D_ROOT:-/workspace/forge3d-ai}"
export RUN_GPU_TESTS=1
export FORGE3D_TEST_API_URL="${FORGE3D_TEST_API_URL:-http://127.0.0.1:8000}"
export FORGE3D_GPU_TEST_TIMEOUT="${FORGE3D_GPU_TEST_TIMEOUT:-1200}"

if [[ -z "${FORGE3D_TEST_IMAGE:-}" || ! -f "${FORGE3D_TEST_IMAGE}" ]]; then
  echo "Defina FORGE3D_TEST_IMAGE para uma imagem existente." >&2
  exit 1
fi

"${ROOT_DIR}/backend/scripts/check_services.sh"
echo "GPU tests api=${FORGE3D_TEST_API_URL} timeout=${FORGE3D_GPU_TEST_TIMEOUT}s pid=$$"
cd "${ROOT_DIR}"
PYTHONPATH=backend python3 -m pytest -m gpu -vv --tb=short
