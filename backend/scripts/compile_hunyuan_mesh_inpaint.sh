#!/usr/bin/env bash
set -euo pipefail

HUNYUAN_ROOT="${HUNYUAN_ROOT:-/workspace/kai3d/models/Hunyuan3D-2.1}"
HUNYUAN_PYTHON="${HUNYUAN_PYTHON:-${HUNYUAN_ROOT}/venv/bin/python}"
CXX="${CXX:-c++}"
RENDERER_DIR="${HUNYUAN_ROOT}/hy3dpaint/DifferentiableRenderer"
SOURCE="${RENDERER_DIR}/mesh_inpaint_processor.cpp"

if [[ ! -x "${HUNYUAN_PYTHON}" ]]; then
  echo "error: HUNYUAN_PYTHON is not executable: ${HUNYUAN_PYTHON}" >&2
  exit 2
fi
if [[ ! -f "${SOURCE}" ]]; then
  echo "error: source not found: ${SOURCE}" >&2
  exit 2
fi
if ! command -v "${CXX}" >/dev/null 2>&1; then
  echo "error: C++ compiler not found: ${CXX}" >&2
  exit 2
fi

"${HUNYUAN_PYTHON}" -c "import pybind11" >/dev/null
EXT_SUFFIX="$("${HUNYUAN_PYTHON}" -c 'import sysconfig; value = sysconfig.get_config_var("EXT_SUFFIX"); assert value; print(value)')"
read -r -a PYBIND11_INCLUDES <<< "$("${HUNYUAN_PYTHON}" -m pybind11 --includes)"
OUTPUT="${RENDERER_DIR}/mesh_inpaint_processor${EXT_SUFFIX}"

echo "python=$("${HUNYUAN_PYTHON}" -c 'import sys; print(sys.executable)')"
echo "python_version=$("${HUNYUAN_PYTHON}" -c 'import platform; print(platform.python_version())')"
echo "extension_suffix=${EXT_SUFFIX}"
echo "output=${OUTPUT}"

"${CXX}" -O3 -Wall -Wextra -shared -std=c++11 -fPIC \
  -include array -include cstdint \
  "${PYBIND11_INCLUDES[@]}" \
  "${SOURCE}" \
  -o "${OUTPUT}"

PYTHONPATH="${HUNYUAN_ROOT}${PYTHONPATH:+:${PYTHONPATH}}" \
  "${HUNYUAN_PYTHON}" \
  "$(dirname "$0")/test_hunyuan_mesh_inpaint.py" \
  --root "${HUNYUAN_ROOT}"
