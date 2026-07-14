#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="${FORGE3D_ROOT:-/workspace/forge3d-ai}"
PORT="${PORT:-8000}"
TRIPOSR_RUN="${FORGE3D_TRIPOSR_RUN:-/workspace/kai3d/models/TripoSR/run.py}"
export FORGE3D_TEXTURE_CACHE="${FORGE3D_TEXTURE_CACHE:-/workspace/.cache/forge3d-texture}"
export TMPDIR="${TMPDIR:-/tmp}"

if [[ ! -f "${TRIPOSR_RUN}" ]]; then
  echo "TripoSR run.py ausente: ${TRIPOSR_RUN}" >&2
  exit 1
fi
if [[ ! -f "${ROOT_DIR}/backend/main.py" ]]; then
  echo "Backend Forge3D ausente: ${ROOT_DIR}" >&2
  exit 1
fi
mkdir -p \
  "${FORGE3D_TEXTURE_CACHE}/cache" \
  "${FORGE3D_TEXTURE_CACHE}/hub" \
  "${FORGE3D_TEXTURE_CACHE}/transformers" \
  "${FORGE3D_TEXTURE_CACHE}/datasets" \
  "${FORGE3D_TEXTURE_CACHE}/torch" \
  "${TMPDIR}"

echo "Forge3D port=${PORT} launcher_pid=$$ root=${ROOT_DIR} texture_cache=${FORGE3D_TEXTURE_CACHE} tmpdir=${TMPDIR}"
exec "${ROOT_DIR}/backend/scripts/start_runpod.sh"
