from __future__ import annotations

import argparse
import errno
import json
import logging
import os
import shutil
import sys
import tempfile
import time
import types
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

LOG = logging.getLogger("forge3d.hunyuan.paint")
DEFAULT_TEXTURE_CACHE = Path("/workspace/.cache/forge3d-texture")
DEFAULT_MIN_FREE_BYTES = 3 * 1024**3
DEFAULT_DOWNLOAD_ATTEMPTS = 4
DEFAULT_RETRY_BASE_SECONDS = 2.0


class TextureCacheError(RuntimeError):
    """Safe cache/download error shown by the wrapper."""


@dataclass(frozen=True)
class CacheLayout:
    root: Path
    cache: Path
    hub: Path
    transformers: Path
    datasets: Path
    torch: Path
    xet: Path
    tmp: Path

    @property
    def ready_marker(self) -> Path:
        return self.root / ".paint_models_ready"


def configure_cache_environment(
    cache_root: Path | str | None = None,
    *,
    environ=None,
) -> CacheLayout:
    """Configure every model cache before importing ML dependencies."""
    environ = os.environ if environ is None else environ
    root = Path(
        cache_root or environ.get("FORGE3D_TEXTURE_CACHE") or DEFAULT_TEXTURE_CACHE
    ).expanduser()
    root = root.resolve()
    tmp = Path(environ.get("TMPDIR") or "/tmp").expanduser().resolve()
    layout = CacheLayout(
        root=root,
        cache=root / "cache",
        hub=root / "hub",
        transformers=root / "transformers",
        datasets=root / "datasets",
        torch=root / "torch",
        xet=root / "xet",
        tmp=tmp,
    )
    try:
        for directory in (
            layout.root,
            layout.cache,
            layout.hub,
            layout.transformers,
            layout.datasets,
            layout.torch,
            layout.xet,
            layout.tmp,
        ):
            directory.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        raise TextureCacheError(
            f"Não foi possível preparar o cache de textura: {layout.root}"
        ) from error
    environ.update(
        {
            "FORGE3D_TEXTURE_CACHE": str(layout.root),
            "HF_HOME": str(layout.cache),
            "HUGGINGFACE_HUB_CACHE": str(layout.hub),
            "HF_HUB_CACHE": str(layout.hub),
            "TRANSFORMERS_CACHE": str(layout.transformers),
            "HF_DATASETS_CACHE": str(layout.datasets),
            "XDG_CACHE_HOME": str(layout.cache),
            "TORCH_HOME": str(layout.torch),
            "DIFFUSERS_CACHE": str(layout.hub),
            "HF_XET_CACHE": str(layout.xet),
            "HF_HUB_DISABLE_XET": "1",
            "TMPDIR": str(layout.tmp),
            "TMP": str(layout.tmp),
            "TEMP": str(layout.tmp),
        }
    )
    environ.setdefault("HF_HUB_DOWNLOAD_TIMEOUT", "600")
    environ.setdefault("HF_HUB_ETAG_TIMEOUT", "30")
    if environ is os.environ:
        tempfile.tempdir = str(layout.tmp)
    return layout


def log_cache_environment(layout: CacheLayout) -> None:
    LOG.info("HF_HOME=%s", layout.cache)
    LOG.info("HUGGINGFACE_HUB_CACHE=%s", layout.hub)
    LOG.info("TRANSFORMERS_CACHE=%s", layout.transformers)
    LOG.info("TMPDIR=%s", layout.tmp)


def ensure_cache_capacity(
    layout: CacheLayout,
    required_bytes: int,
    *,
    disk_usage: Callable = shutil.disk_usage,
) -> None:
    probe = layout.root / ".write_probe"
    try:
        probe.write_bytes(b"forge3d-cache-probe")
    except OSError as error:
        raise TextureCacheError(
            f"Cache de textura sem permissão ou quota disponível: {layout.root}"
        ) from error
    finally:
        probe.unlink(missing_ok=True)
    if layout.ready_marker.is_file():
        return
    free_bytes = disk_usage(layout.root).free
    if free_bytes < required_bytes:
        required_gib = required_bytes / 1024**3
        free_gib = free_bytes / 1024**3
        raise TextureCacheError(
            "Espaço insuficiente no cache de textura: "
            f"necessário={required_gib:.1f}GiB disponível={free_gib:.1f}GiB"
        )


def _is_quota_error(error: BaseException) -> bool:
    return isinstance(error, OSError) and error.errno in {errno.EDQUOT, errno.ENOSPC}


def _is_retryable_download_error(error: BaseException) -> bool:
    if isinstance(error, (ConnectionError, TimeoutError, OSError)):
        return True
    name = type(error).__name__.lower()
    return any(marker in name for marker in ("connection", "timeout", "httperror"))


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


def install_bpy_compatibility() -> None:
    """
    O Paint usa load_mesh/save_mesh do módulo real mesh_utils.

    Como save_glb=False, bpy não deve ser utilizado durante esta etapa.
    Criamos apenas um módulo bpy vazio para permitir o import do mesh_utils real.
    """

    if "bpy" not in sys.modules:
        sys.modules["bpy"] = types.ModuleType("bpy")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Forge3D Hunyuan Paint Wrapper")

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

    parser.add_argument(
        "--cache-dir",
        default=os.getenv("FORGE3D_TEXTURE_CACHE", str(DEFAULT_TEXTURE_CACHE)),
    )

    return parser.parse_args()


def build_pipeline(root: Path, resolution: int):
    install_torchvision_compatibility()
    install_bpy_compatibility()

    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

    hy3dpaint = root / "hy3dpaint"

    if str(hy3dpaint) not in sys.path:
        sys.path.insert(0, str(hy3dpaint))

    from hy3dpaint.textureGenPipeline import (
        Hunyuan3DPaintConfig,
        Hunyuan3DPaintPipeline,
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

    conf.custom_pipeline = str(root / "hy3dpaint" / "hunyuanpaintpbr")

    return Hunyuan3DPaintPipeline(conf)


def load_pipeline_with_retry(
    root: Path,
    resolution: int,
    layout: CacheLayout,
    *,
    builder: Callable = build_pipeline,
    sleeper: Callable[[float], None] = time.sleep,
    environ=None,
):
    environ = os.environ if environ is None else environ
    attempts = max(
        1,
        int(
            environ.get("FORGE3D_TEXTURE_DOWNLOAD_ATTEMPTS", DEFAULT_DOWNLOAD_ATTEMPTS)
        ),
    )
    retry_base = max(
        0.0,
        float(
            environ.get(
                "FORGE3D_TEXTURE_DOWNLOAD_RETRY_SECONDS",
                DEFAULT_RETRY_BASE_SECONDS,
            )
        ),
    )
    required_bytes = max(
        0,
        int(
            environ.get(
                "FORGE3D_TEXTURE_MIN_FREE_BYTES",
                DEFAULT_MIN_FREE_BYTES,
            )
        ),
    )
    ensure_cache_capacity(layout, required_bytes)
    for attempt in range(attempts):
        try:
            pipeline = builder(root, resolution)
            layout.ready_marker.touch()
            return pipeline
        except Exception as error:
            if _is_quota_error(error):
                raise TextureCacheError(
                    "Quota excedida durante o download do Hunyuan Paint. "
                    f"Cache configurado: {layout.root}"
                ) from error
            if not _is_retryable_download_error(error):
                raise
            if attempt + 1 >= attempts:
                raise TextureCacheError(
                    "Download do Hunyuan Paint interrompido após retries. "
                    "Os arquivos parciais foram preservados para retomada."
                ) from error
            delay = retry_base * (2**attempt)
            LOG.warning(
                "Carregamento do Paint interrompido; retomando pelo cache "
                "attempt=%s/%s delay=%.1fs error=%s",
                attempt + 1,
                attempts,
                delay,
                type(error).__name__,
            )
            sleeper(delay)
    raise RuntimeError("unreachable")


def run_pipeline(
    root: Path,
    mesh: Path,
    image: Path,
    output: Path,
    resolution: int,
    cache_layout: CacheLayout,
):
    pipeline = load_pipeline_with_retry(root, resolution, cache_layout)

    output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    result = pipeline(
        mesh_path=str(mesh),
        image_path=str(image),
        output_mesh_path=str(output),
        use_remesh=False,
        save_glb=False,
    )

    return result


def ensure_output_exists(output: Path):
    if output.exists():
        return

    raise FileNotFoundError(f"Arquivo não gerado: {output}")


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
        "output_size_bytes": (output.stat().st_size if output.exists() else 0),
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
        raise FileNotFoundError(f"Raiz Hunyuan não encontrada: {root}")

    if not mesh.is_file():
        raise FileNotFoundError(f"Mesh não encontrada: {mesh}")

    if not image.is_file():
        raise FileNotFoundError(f"Imagem não encontrada: {image}")

    if output.suffix.lower() != ".obj":
        raise ValueError("A saída do Paint deve ser um arquivo .obj")


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
        Path(args.metadata).expanduser().resolve() if args.metadata else None
    )

    try:
        cache_layout = configure_cache_environment(args.cache_dir)
        log_cache_environment(cache_layout)
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
            cache_layout=cache_layout,
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
