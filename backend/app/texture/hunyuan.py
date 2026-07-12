from __future__ import annotations

import json
import time
from pathlib import Path

from app.core.config import Settings
from app.core.exceptions import ArtifactNotFoundError, ServiceUnavailableError
from app.engines.contracts import JobContext
from app.infrastructure.subprocess_runner import ProcessRunner
from app.texture.contracts import TextureRequest, TextureResult


class HunyuanTextureService:
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

    def _template(self) -> list[str]:
        if not self.settings.texture_command_json.strip():
            raise ServiceUnavailableError("Comando Hunyuan Texture não configurado")
        try:
            command = json.loads(self.settings.texture_command_json)
        except json.JSONDecodeError as exc:
            raise ServiceUnavailableError("Comando Hunyuan Texture inválido") from exc
        if not isinstance(command, list) or not all(
            isinstance(item, str) for item in command
        ):
            raise ServiceUnavailableError("Comando Hunyuan Texture inválido")
        return command

    def available(self) -> bool:
        try:
            return bool(self._template()) and self.settings.texture_root.is_dir()
        except ServiceUnavailableError:
            return False

    def texture(
        self,
        job_context: JobContext,
        mesh_path: Path,
        reference_image: Path,
        request: TextureRequest,
    ) -> TextureResult:
        template = self._template()
        if not mesh_path.is_file():
            raise ArtifactNotFoundError("Malha original não encontrada")
        if not reference_image.is_file():
            raise ArtifactNotFoundError("Imagem de referência não encontrada")
        output = job_context.job_dir / "model_textured.glb"
        values = {
            "mesh": str(mesh_path),
            "image": str(reference_image),
            "output": str(output),
            "resolution": str(request.resolution),
            "quality": request.quality,
        }
        command = [item.format(**values) for item in template]
        started = time.monotonic()
        result = self.runner.run(command, timeout=self.settings.texture_timeout_seconds)
        if result.returncode != 0:
            raise ServiceUnavailableError("Hunyuan Texture falhou")
        if not output.is_file() or output.stat().st_size <= 0:
            raise ArtifactNotFoundError("model_textured.glb não foi gerado")
        maps = sorted(
            {
                path.stem.lower()
                for path in job_context.job_dir.rglob("*")
                if path.is_file() and path.stem.lower() in self.pbr_maps
            }
        )
        return TextureResult(
            job_id=job_context.job_id,
            status="textured",
            input_mesh=mesh_path,
            artifact_path=output,
            artifact_relative_path="model_textured.glb",
            format="glb",
            metadata={
                "resolution": request.resolution,
                "quality": request.quality,
                "duration_seconds": round(time.monotonic() - started, 3),
                "size_bytes": output.stat().st_size,
                "maps": maps,
                "engine": self.name,
                "pipeline_version": self.settings.texture_pipeline_version,
            },
        )
