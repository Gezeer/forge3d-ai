#!/usr/bin/env bash
set -euo pipefail

HUNYUAN_ROOT="${HUNYUAN_ROOT:-/workspace/kai3d/models/Hunyuan3D-2.1}"
HUNYUAN_PORT="${HUNYUAN_PORT:-8080}"

if [[ ! -d "${HUNYUAN_ROOT}" ]]; then
  echo "Hunyuan root ausente: ${HUNYUAN_ROOT}" >&2
  exit 1
fi
if [[ -z "${HUNYUAN_START_COMMAND:-}" ]]; then
  echo "Defina HUNYUAN_START_COMMAND com o comando validado no RunPod." >&2
  exit 1
fi

echo "Hunyuan port=${HUNYUAN_PORT} launcher_pid=$$ root=${HUNYUAN_ROOT}"
cd "${HUNYUAN_ROOT}"
exec bash -lc "${HUNYUAN_START_COMMAND}"
