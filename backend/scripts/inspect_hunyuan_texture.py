#!/usr/bin/env python3
"""Diagnose Hunyuan Paint on RunPod without installing dependencies."""

import argparse
import ast
import importlib.util
import os
import shutil
import subprocess
from pathlib import Path


def check_import(name):
    try:
        __import__(name)
        return "ok"
    except Exception as error:
        return f"missing:{type(error).__name__}"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        default=os.getenv(
            "FORGE3D_TEXTURE_ROOT", "/workspace/kai3d/models/Hunyuan3D-2.1"
        ),
    )
    args = parser.parse_args()
    root = Path(args.root)
    files = [
        root / "hy3dpaint/textureGenPipeline.py",
        root / "gradio_app.py",
        root / "requirements.txt",
    ]
    failed = False
    for path in files:
        print(f"file {path.name}: {'ok' if path.is_file() else 'missing'}")
        failed |= not path.is_file()
        if path.suffix == ".py" and path.is_file():
            tree = ast.parse(path.read_text(errors="replace"))
            imports = sorted(
                {
                    node.names[0].name
                    for node in ast.walk(tree)
                    if isinstance(node, (ast.Import, ast.ImportFrom)) and node.names
                }
            )
            relevant = [
                name
                for name in imports
                if any(
                    key in name.lower()
                    for key in ("bpy", "pymeshlab", "render", "hy3dpaint")
                )
            ]
            print(f"  relevant_imports={','.join(relevant) or 'none'}")
    for module in ("bpy", "pymeshlab"):
        state = check_import(module)
        print(f"import {module}: {state}")
        failed |= state != "ok"
    renderer = importlib.util.find_spec("hy3dpaint") is not None
    print(f"DifferentiableRenderer/pipeline importable: {renderer}")
    failed |= not renderer
    libraries = (
        subprocess.run(
            ["sh", "-c", "ldconfig -p 2>/dev/null | grep -q 'libOpenGL.so.0'"],
            check=False,
        ).returncode
        == 0
    )
    print(f"libOpenGL.so.0: {'ok' if libraries else 'missing'}")
    failed |= not libraries
    if shutil.which("nvidia-smi"):
        gpu = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,memory.total,memory.free",
                "--format=csv,noheader",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        print("cuda/vram:", gpu.stdout.strip() or "unavailable")
        failed |= gpu.returncode != 0
    else:
        print("cuda/vram: nvidia-smi missing")
        failed = True
    weights = list(root.glob("**/*paint*")) + list(root.glob("**/*texture*"))
    print(f"texture weights/candidates: {len(weights)}")
    failed |= not weights
    for name in ("HF_HOME", "TORCH_HOME", "XDG_CACHE_HOME"):
        value = os.getenv(name)
        print(f"cache {name}: {'configured' if value else 'default'}")
    print(
        "FORGE3D_TEXTURE_COMMAND_JSON must describe the official command after inspection."
    )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
