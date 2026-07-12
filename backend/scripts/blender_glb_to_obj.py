"""Convert a GLB mesh to OBJ from Blender's background mode."""

import argparse
import sys
from pathlib import Path

import bpy


def arguments() -> argparse.Namespace:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    return parser.parse_args(argv)


def reset_scene() -> None:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)


def export_obj(output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    if hasattr(bpy.ops.wm, "obj_export"):
        bpy.ops.wm.obj_export(
            filepath=str(output), export_materials=True, path_mode="COPY"
        )
    else:
        bpy.ops.export_scene.obj(
            filepath=str(output), use_materials=True, path_mode="COPY"
        )


def main() -> int:
    args = arguments()
    source = Path(args.input).expanduser().resolve()
    output = Path(args.output).expanduser().resolve()
    if not source.is_file() or source.suffix.lower() != ".glb":
        raise FileNotFoundError(f"GLB input not found: {source}")
    if output.suffix.lower() != ".obj":
        raise ValueError("Output must use the .obj extension")
    reset_scene()
    bpy.ops.import_scene.gltf(filepath=str(source))
    export_obj(output)
    if not output.is_file() or output.stat().st_size <= 0:
        raise RuntimeError("Blender did not generate the OBJ artifact")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
