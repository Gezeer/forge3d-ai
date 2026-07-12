#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="${FORGE3D_ROOT:-/workspace/forge3d-ai}"
PYTHONPATH="${ROOT_DIR}/backend" python3 "${ROOT_DIR}/backend/scripts/inspect_hunyuan_texture.py" --root "${FORGE3D_TEXTURE_ROOT:-/workspace/kai3d/models/Hunyuan3D-2.1}"
