"""Convert a textured OBJ and its materials to an embedded GLB."""

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


def import_obj(source: Path) -> None:
    if hasattr(bpy.ops.wm, "obj_import"):
        bpy.ops.wm.obj_import(filepath=str(source))
    else:
        bpy.ops.import_scene.obj(filepath=str(source))


def main() -> int:
    args = arguments()
    source = Path(args.input).expanduser().resolve()
    output = Path(args.output).expanduser().resolve()
    if not source.is_file() or source.suffix.lower() != ".obj":
        raise FileNotFoundError(f"OBJ input not found: {source}")
    if output.suffix.lower() != ".glb":
        raise ValueError("Output must use the .glb extension")
    output.parent.mkdir(parents=True, exist_ok=True)
    reset_scene()
    import_obj(source)
    bpy.ops.export_scene.gltf(
        filepath=str(output),
        export_format="GLB",
        export_materials="EXPORT",
        export_image_format="AUTO",
    )
    if not output.is_file() or output.stat().st_size <= 0:
        raise RuntimeError("Blender did not generate the GLB artifact")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
