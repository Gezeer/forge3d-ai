#!/usr/bin/env python3
"""Smoke-test the official Hunyuan mesh inpaint pybind11 extension."""

import argparse
import importlib
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        default="/workspace/kai3d/models/Hunyuan3D-2.1",
        help="Hunyuan3D-2.1 checkout root",
    )
    parser.add_argument(
        "--functional",
        action="store_true",
        help="also execute meshVerticeInpaint with a minimal NumPy fixture",
    )
    args = parser.parse_args()

    root = Path(args.root).resolve()
    if not (root / "hy3dpaint").is_dir():
        parser.error(f"hy3dpaint package not found below {root}")
    sys.path.insert(0, str(root))

    module = importlib.import_module(
        "hy3dpaint.DifferentiableRenderer.mesh_inpaint_processor"
    )
    function = getattr(module, "meshVerticeInpaint")
    if not callable(function):
        raise TypeError("meshVerticeInpaint is not callable")

    print("import=ok")
    print(f"module={module.__name__}")
    print(f"function={function.__name__}")

    if args.functional:
        import numpy as np

        texture = np.zeros((2, 2, 3), dtype=np.float32)
        mask = np.ones((2, 2), dtype=np.uint8)
        vertices = np.array(
            [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]],
            dtype=np.float32,
        )
        uv = np.array([[0.0, 0.0], [1.0, 0.0], [0.0, 1.0]], dtype=np.float32)
        indices = np.array([[0, 1, 2]], dtype=np.int32)
        output = function(texture, mask, vertices, uv, indices, indices, "smooth")
        if not isinstance(output, tuple) or len(output) != 2:
            raise TypeError("unexpected meshVerticeInpaint return contract")
        print("functional=ok")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
