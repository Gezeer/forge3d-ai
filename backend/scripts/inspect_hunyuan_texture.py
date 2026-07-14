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
    cache_root = Path(
        os.getenv("FORGE3D_TEXTURE_CACHE", "/workspace/.cache/forge3d-texture")
    ).expanduser()
    tmp_dir = Path(os.getenv("TMPDIR", "/tmp")).expanduser()
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
    expected_cache = {
        "HF_HOME": cache_root / "cache",
        "HUGGINGFACE_HUB_CACHE": cache_root / "hub",
        "TRANSFORMERS_CACHE": cache_root / "transformers",
        "HF_DATASETS_CACHE": cache_root / "datasets",
        "XDG_CACHE_HOME": cache_root / "cache",
        "TORCH_HOME": cache_root / "torch",
    }
    print(f"FORGE3D_TEXTURE_CACHE: {cache_root}")
    for name, expected in expected_cache.items():
        current = os.getenv(name)
        state = "configured" if current == str(expected) else "wrapper-managed"
        print(f"cache {name}: {state} target={expected}")
    print(f"TMPDIR: {tmp_dir}")
    try:
        cache_root.mkdir(parents=True, exist_ok=True)
        probe = cache_root / ".diagnostic-write-probe"
        probe.write_bytes(b"forge3d")
        probe.unlink()
        free = shutil.disk_usage(cache_root).free
        print(f"texture cache writable: yes free_bytes={free}")
    except OSError as error:
        print(f"texture cache writable: no error={type(error).__name__}")
        failed = True
    print("HuggingFace Xet is disabled by the Paint wrapper to avoid quota crashes.")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
