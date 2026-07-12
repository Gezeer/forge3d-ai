#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="${FORGE3D_ROOT:-/workspace/forge3d-ai}"
"${ROOT_DIR}/backend/scripts/check_texture_dependencies.sh"
if [[ -z "${HUNYUAN_TEXTURE_START_COMMAND:-}" ]]; then
  echo "Defina HUNYUAN_TEXTURE_START_COMMAND após confirmar o comando oficial." >&2
  exit 1
fi
echo "Hunyuan texture launcher_pid=$$ root=${FORGE3D_TEXTURE_ROOT:-/workspace/kai3d/models/Hunyuan3D-2.1}"
exec bash -lc "${HUNYUAN_TEXTURE_START_COMMAND}"
