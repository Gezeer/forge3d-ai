#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="${FORGE3D_ROOT:-/workspace/forge3d-ai}"
PORT="${PORT:-8000}"
TRIPOSR_RUN="${FORGE3D_TRIPOSR_RUN:-/workspace/kai3d/models/TripoSR/run.py}"

if [[ ! -f "${TRIPOSR_RUN}" ]]; then
  echo "TripoSR run.py ausente: ${TRIPOSR_RUN}" >&2
  exit 1
fi
if [[ ! -f "${ROOT_DIR}/backend/main.py" ]]; then
  echo "Backend Forge3D ausente: ${ROOT_DIR}" >&2
  exit 1
fi

echo "Forge3D port=${PORT} launcher_pid=$$ root=${ROOT_DIR}"
exec "${ROOT_DIR}/backend/scripts/start_runpod.sh"
