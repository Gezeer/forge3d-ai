from __future__ import annotations

import json
import logging
import shutil
import time
from pathlib import Path
from typing import Sequence

from app.core.config import Settings
from app.core.exceptions import ArtifactNotFoundError, TexturePipelineError
from app.engines.contracts import JobContext
from app.infrastructure.subprocess_runner import ProcessResult, ProcessRunner
from app.texture.contracts import TextureRequest, TextureResult

logger = logging.getLogger("forge3d.texture")


class HunyuanTextureService:
    """Orchestrate the validated GLB -> OBJ -> Paint -> GLB pipeline."""

    name = "hunyuan"
    pbr_maps = {
        "albedo",
        "basecolor",
        "base_color",
        "normal",
        "roughness",
        "metallic",
        "occlusion",
        "emissive",
    }

    def __init__(self, settings: Settings, runner: ProcessRunner) -> None:
        self.settings = settings
        self.runner = runner

    @property
    def scripts_dir(self) -> Path:
        return self.settings.forge3d_root / "backend" / "scripts"

    def available(self) -> bool:
        required = (
            self.settings.texture_root,
            self.settings.texture_python,
            self.scripts_dir / "run_hunyuan_paint.py",
            self.scripts_dir / "blender_glb_to_obj.py",
            self.scripts_dir / "blender_obj_to_glb.py",
        )
        return (
            required[0].is_dir()
            and all(path.is_file() for path in required[1:])
            and shutil.which(self.settings.blender_executable) is not None
        )

    def _run_step(self, step: str, command: Sequence[str]) -> ProcessResult:
        try:
            result = self.runner.run(
                command, timeout=self.settings.texture_timeout_seconds
            )
        except Exception as exc:
            logger.error("[Texture] Failed step=%s error=%s", step, type(exc).__name__)
            raise TexturePipelineError(step, f"Falha na etapa {step}") from exc
        if result.returncode != 0:
            details = result.stderr if self.settings.expose_process_details else ""
            logger.error(
                "[Texture] Failed step=%s returncode=%s", step, result.returncode
            )
            raise TexturePipelineError(step, f"Falha na etapa {step}", details=details)
        return result

    @staticmethod
    def _require_artifact(path: Path, step: str) -> Path:
        if not path.is_file() or path.stat().st_size <= 0:
            raise TexturePipelineError(step, f"Artefato não gerado: {path.name}")
        return path

    def convert_glb_to_obj(self, glb_path: Path, output_obj: Path) -> Path:
        logger.info("[Texture] Converting GLB")
        output_obj.unlink(missing_ok=True)
        command = [
            self.settings.blender_executable,
            "-b",
            "--python",
            str(self.scripts_dir / "blender_glb_to_obj.py"),
            "--",
            "--input",
            str(glb_path),
            "--output",
            str(output_obj),
        ]
        self._run_step("glb_to_obj", command)
        return self._require_artifact(output_obj, "glb_to_obj")

    def paint_mesh(
        self,
        input_obj: Path,
        reference_image: Path,
        output_obj: Path,
        request: TextureRequest,
        metadata_path: Path,
    ) -> Path:
        logger.info("[Texture] Running Paint")
        output_obj.unlink(missing_ok=True)
        command = [
            str(self.settings.texture_python),
            str(self.scripts_dir / "run_hunyuan_paint.py"),
            "--root",
            str(self.settings.texture_root),
            "--mesh",
            str(input_obj),
            "--image",
            str(reference_image),
            "--output",
            str(output_obj),
            "--resolution",
            str(request.resolution),
            "--quality",
            request.quality,
            "--metadata",
            str(metadata_path),
        ]
        self._run_step("paint", command)
        logger.info("[Texture] Paint finished")
        return self._require_artifact(output_obj, "paint")

    def convert_obj_to_glb(self, obj_path: Path, output_glb: Path) -> Path:
        logger.info("[Texture] Converting OBJ")
        output_glb.unlink(missing_ok=True)
        command = [
            self.settings.blender_executable,
            "-b",
            "--python",
            str(self.scripts_dir / "blender_obj_to_glb.py"),
            "--",
            "--input",
            str(obj_path),
            "--output",
            str(output_glb),
        ]
        self._run_step("obj_to_glb", command)
        return self._require_artifact(output_glb, "obj_to_glb")

    def generate_texture(
        self,
        job_context: JobContext,
        mesh_path: Path,
        reference_image: Path,
        request: TextureRequest,
    ) -> TextureResult:
        if not mesh_path.is_file():
            raise ArtifactNotFoundError("Malha original não encontrada")
        if mesh_path.suffix.lower() != ".glb":
            raise TexturePipelineError("glb_to_obj", "A entrada deve ser GLB")
        if not reference_image.is_file():
            raise ArtifactNotFoundError("Imagem de referência não encontrada")

        started = time.monotonic()
        job_dir = job_context.job_dir
        work_dir = job_dir / "texture_work"
        if work_dir.exists():
            shutil.rmtree(work_dir)
        work_dir.mkdir(parents=True)
        white_obj = work_dir / "white_mesh.obj"
        textured_obj = work_dir / "textured_mesh.obj"
        output_glb = job_dir / "model_textured.glb"
        paint_metadata = work_dir / "paint_metadata.json"
        metadata_path = job_dir / "texture_metadata.json"

        self.convert_glb_to_obj(mesh_path, white_obj)
        self.paint_mesh(
            white_obj, reference_image, textured_obj, request, paint_metadata
        )
        self.convert_obj_to_glb(textured_obj, output_glb)

        maps = sorted(
            {
                path.stem.lower()
                for path in work_dir.rglob("*")
                if path.is_file() and path.stem.lower() in self.pbr_maps
            }
        )
        metadata = {
            "status": "completed",
            "engine": self.name,
            "pipeline_version": self.settings.texture_pipeline_version,
            "resolution": request.resolution,
            "quality": request.quality,
            "duration_seconds": round(time.monotonic() - started, 3),
            "size_bytes": output_glb.stat().st_size,
            "maps": maps,
            "output": "model_textured.glb",
        }
        temporary_metadata = metadata_path.with_suffix(".json.tmp")
        temporary_metadata.write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        temporary_metadata.replace(metadata_path)
        logger.info(
            "[Texture] Finished job_id=%s size=%s duration=%.3f",
            job_context.job_id,
            output_glb.stat().st_size,
            metadata["duration_seconds"],
        )
        return TextureResult(
            job_id=job_context.job_id,
            status="completed",
            input_mesh=mesh_path,
            artifact_path=output_glb,
            artifact_relative_path="model_textured.glb",
            format="glb",
            metadata=metadata,
        )

    def texture(
        self,
        job_context: JobContext,
        mesh_path: Path,
        reference_image: Path,
        request: TextureRequest,
    ) -> TextureResult:
        return self.generate_texture(job_context, mesh_path, reference_image, request)
