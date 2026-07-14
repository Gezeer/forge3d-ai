#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="${FORGE3D_ROOT:-/workspace/forge3d-ai}"
export FORGE3D_TEXTURE_CACHE="${FORGE3D_TEXTURE_CACHE:-/workspace/.cache/forge3d-texture}"
export TMPDIR="${TMPDIR:-/tmp}"
mkdir -p \
  "${FORGE3D_TEXTURE_CACHE}/cache" \
  "${FORGE3D_TEXTURE_CACHE}/hub" \
  "${FORGE3D_TEXTURE_CACHE}/transformers" \
  "${FORGE3D_TEXTURE_CACHE}/datasets" \
  "${FORGE3D_TEXTURE_CACHE}/torch" \
  "${TMPDIR}"
"${ROOT_DIR}/backend/scripts/check_texture_dependencies.sh"
if [[ -z "${HUNYUAN_TEXTURE_START_COMMAND:-}" ]]; then
  echo "Defina HUNYUAN_TEXTURE_START_COMMAND após confirmar o comando oficial." >&2
  exit 1
fi
echo "Hunyuan texture launcher_pid=$$ root=${FORGE3D_TEXTURE_ROOT:-/workspace/kai3d/models/Hunyuan3D-2.1} cache=${FORGE3D_TEXTURE_CACHE} tmpdir=${TMPDIR}"
exec bash -lc "${HUNYUAN_TEXTURE_START_COMMAND}"
