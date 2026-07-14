#!/usr/bin/env bash
set -euo pipefail

HUNYUAN_ROOT="${FORGE3D_HUNYUAN_ROOT:-/workspace/kai3d/models/Hunyuan3D-2.1}"
HUNYUAN_PYTHON="${FORGE3D_HUNYUAN_PYTHON:-/workspace/kai3d/models/Hunyuan3D-2.1/venv/bin/python}"
HUNYUAN_PORT="${FORGE3D_HUNYUAN_PORT:-8080}"
HUNYUAN_CACHE="${FORGE3D_HUNYUAN_CACHE_PATH:-/tmp/hunyuan-cache}"

if [[ ! -d "${HUNYUAN_ROOT}" ]]; then
  echo "Hunyuan root ausente: ${HUNYUAN_ROOT}" >&2
  exit 1
fi
if [[ ! -x "${HUNYUAN_PYTHON}" || ! -f "${HUNYUAN_ROOT}/gradio_app.py" ]]; then
  echo "Python ou gradio_app.py do Hunyuan ausente." >&2
  exit 1
fi
mkdir -p "${HUNYUAN_CACHE}"

echo "Hunyuan port=${HUNYUAN_PORT} launcher_pid=$$ root=${HUNYUAN_ROOT} cache=${HUNYUAN_CACHE}"
cd "${HUNYUAN_ROOT}"
exec "${HUNYUAN_PYTHON}" gradio_app.py \
  --host 0.0.0.0 \
  --port "${HUNYUAN_PORT}" \
  --cache-path "${HUNYUAN_CACHE}"
