from __future__ import annotations

import argparse
import json
import logging
import sys
import types
from pathlib import Path

LOG = logging.getLogger("forge3d.hunyuan.paint")

def install_torchvision_compatibility() -> None:
    try:
        import torchvision.transforms.functional as functional
    except ImportError:
        return

    module_name = "torchvision.transforms.functional_tensor"

    if module_name in sys.modules:
        return

    compatibility_module = types.ModuleType(module_name)

    for name in dir(functional):
        if not name.startswith("_"):
            setattr(
                compatibility_module,
                name,
                getattr(functional, name),
            )

    sys.modules[module_name] = compatibility_module

def install_mesh_utils_shim() -> None:
    """
    O Hunyuan importa convert_obj_to_glb mesmo quando save_glb=False.

    Criamos um módulo fake apenas para satisfazer o import.
    """

    module = types.ModuleType("DifferentiableRenderer.mesh_utils")

    def convert_obj_to_glb(*args, **kwargs):
        raise RuntimeError(
            "convert_obj_to_glb() não deveria ser chamado quando save_glb=False"
        )

    module.convert_obj_to_glb = convert_obj_to_glb

    sys.modules["DifferentiableRenderer.mesh_utils"] = module


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Forge3D Hunyuan Paint Wrapper"
    )

    parser.add_argument(
        "--root",
        required=True,
        help="Diretório raiz do Hunyuan3D-2.1",
    )

    parser.add_argument(
        "--mesh",
        required=True,
        help="OBJ branco",
    )

    parser.add_argument(
        "--image",
        required=True,
        help="Imagem de referência",
    )

    parser.add_argument(
        "--output",
        required=True,
        help="OBJ texturizado de saída",
    )

    parser.add_argument(
        "--resolution",
        type=int,
        default=768,
    )

    parser.add_argument(
        "--quality",
        choices=[
            "fast",
            "standard",
            "high",
        ],
        default="standard",
    )

    parser.add_argument(
        "--metadata",
        default=None,
    )

    return parser.parse_args()


def build_pipeline(root: Path, resolution: int):
    install_torchvision_compatibility()
    install_mesh_utils_shim()

    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

    hy3dpaint = root / "hy3dpaint"

    if str(hy3dpaint) not in sys.path:
        sys.path.insert(0, str(hy3dpaint))

    from hy3dpaint.textureGenPipeline import (
        Hunyuan3DPaintPipeline,
        Hunyuan3DPaintConfig,
    )

    conf = Hunyuan3DPaintConfig(
        max_num_view=8,
        resolution=resolution,
    )

    conf.realesrgan_ckpt_path = str(
        root / "hy3dpaint" / "ckpt" / "RealESRGAN_x4plus.pth"
    )

    conf.multiview_cfg_path = str(
        root / "hy3dpaint" / "cfgs" / "hunyuan-paint-pbr.yaml"
    )

    conf.custom_pipeline = str(
        root / "hy3dpaint" / "hunyuanpaintpbr"
    )

    return Hunyuan3DPaintPipeline(conf)


def run_pipeline(
    root: Path,
    mesh: Path,
    image: Path,
    output: Path,
    resolution: int,
):
    pipeline = build_pipeline(root, resolution)

    output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    result = pipeline(
        mesh_path=str(mesh),
        image_path=str(image),
        output_mesh_path=str(output),
        save_glb=False,
    )

    return result


def ensure_output_exists(output: Path):
    if output.exists():
        return

    raise FileNotFoundError(
        f"Arquivo não gerado: {output}"
    )


def write_metadata(
    metadata_path: Path | None,
    *,
    root: Path,
    mesh: Path,
    image: Path,
    output: Path,
    resolution: int,
    quality: str,
) -> None:
    if metadata_path is None:
        return

    metadata_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    payload = {
        "engine": "hunyuan-paint",
        "pipeline": "hunyuan3d-2.1",
        "resolution": resolution,
        "quality": quality,
        "output_name": output.name,
        "output_size_bytes": (
            output.stat().st_size
            if output.exists()
            else 0
        ),
    }

    metadata_path.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def validate_inputs(
    root: Path,
    mesh: Path,
    image: Path,
    output: Path,
) -> None:
    if not root.is_dir():
        raise FileNotFoundError(
            f"Raiz Hunyuan não encontrada: {root}"
        )

    if not mesh.is_file():
        raise FileNotFoundError(
            f"Mesh não encontrada: {mesh}"
        )

    if not image.is_file():
        raise FileNotFoundError(
            f"Imagem não encontrada: {image}"
        )

    if output.suffix.lower() != ".obj":
        raise ValueError(
            "A saída do Paint deve ser um arquivo .obj"
        )


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s %(name)s %(message)s",
    )

    args = parse_args()

    root = Path(args.root).expanduser().resolve()
    mesh = Path(args.mesh).expanduser().resolve()
    image = Path(args.image).expanduser().resolve()
    output = Path(args.output).expanduser().resolve()

    metadata_path = (
        Path(args.metadata).expanduser().resolve()
        if args.metadata
        else None
    )

    try:
        validate_inputs(
            root,
            mesh,
            image,
            output,
        )

        LOG.info(
            "Iniciando Hunyuan Paint: quality=%s resolution=%s",
            args.quality,
            args.resolution,
        )

        result = run_pipeline(
            root=root,
            mesh=mesh,
            image=image,
            output=output,
            resolution=args.resolution,
        )

        result_path = Path(result).expanduser().resolve()

        if result_path != output and result_path.is_file():
            output = result_path

        ensure_output_exists(output)

        write_metadata(
            metadata_path,
            root=root,
            mesh=mesh,
            image=image,
            output=output,
            resolution=args.resolution,
            quality=args.quality,
        )

        LOG.info(
            "Textura concluída: output=%s size=%s",
            output.name,
            output.stat().st_size,
        )

        print(
            json.dumps(
                {
                    "status": "success",
                    "output": str(output),
                    "size_bytes": output.stat().st_size,
                },
                ensure_ascii=False,
            )
        )

        return 0

    except Exception as exc:
        LOG.error(
            "Falha no Hunyuan Paint: %s",
            type(exc).__name__,
        )

        print(
            json.dumps(
                {
                    "status": "error",
                    "error_type": type(exc).__name__,
                    "message": str(exc),
                },
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )

        return 1


if __name__ == "__main__":
    raise SystemExit(main())