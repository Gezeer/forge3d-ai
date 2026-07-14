from __future__ import annotations

import shutil
import time
from pathlib import Path
from typing import Any, Iterator
from urllib.parse import unquote, urlparse

from app.core.config import Settings
from app.core.exceptions import ArtifactNotFoundError
from app.domain.generation import GenerationResult
from app.engines.contracts import EngineHealth, JobContext
from app.gpu.lock import GPULock
from app.hunyuan.process_manager import HunyuanProcessManager
from app.infrastructure.hunyuan_client import HunyuanClient
from app.infrastructure.storage import LocalStorage


class HunyuanService:
    name = "hunyuan"
    supported_artifacts = {".glb", ".obj", ".ply", ".stl"}

    def __init__(
        self,
        settings: Settings,
        storage: LocalStorage,
        client: HunyuanClient,
        downloader=None,
        gpu_lock: GPULock | None = None,
        process_manager: HunyuanProcessManager | None = None,
    ) -> None:
        self.settings = settings
        self.storage = storage
        self.client = client
        self.downloader = downloader or self._download
        self.gpu_lock = gpu_lock
        self.process_manager = process_manager

    def _values(self, value: Any) -> Iterator[Any]:
        if isinstance(value, dict):
            for item in value.values():
                yield from self._values(item)
        elif isinstance(value, (list, tuple)):
            for item in value:
                yield from self._values(item)
        else:
            yield value

    def _artifact_from_result(self, result: Any) -> tuple[str, str, str]:
        for value in self._values(result):
            if isinstance(value, Path):
                candidate = value
            elif isinstance(value, str):
                parsed = urlparse(value)
                if parsed.scheme in {"http", "https"}:
                    suffix = Path(unquote(parsed.path)).suffix.lower()
                    if suffix in self.supported_artifacts:
                        return "remote", value, Path(unquote(parsed.path)).name
                candidate = Path(value)
            else:
                continue
            if (
                candidate.suffix.lower() in self.supported_artifacts
                and candidate.is_file()
            ):
                return "local", str(candidate), candidate.name
        raise ArtifactNotFoundError(
            "O Hunyuan respondeu, mas nenhum artefato 3D local foi encontrado"
        )

    def _download(self, url: str, destination: Path) -> None:
        import httpx

        with httpx.stream(
            "GET", url, timeout=self.settings.generation_timeout_seconds
        ) as response:
            response.raise_for_status()
            with destination.open("wb") as target:
                for chunk in response.iter_bytes():
                    target.write(chunk)

    def _materialize(
        self, kind: str, source: str, original_name: str, job_dir: Path
    ) -> Path:
        safe_name = self.storage.safe_filename(original_name)
        suffix = Path(safe_name).suffix.lower()
        if suffix not in self.supported_artifacts:
            raise ArtifactNotFoundError("Formato de artefato Hunyuan inválido")
        destination = job_dir / f"model{suffix}"
        if kind == "remote":
            self.downloader(source, destination)
        else:
            local_source = Path(source)
            if local_source.resolve() != destination.resolve():
                shutil.copy2(local_source, destination)
        if not destination.is_file() or destination.stat().st_size <= 0:
            raise ArtifactNotFoundError("Artefato Hunyuan vazio ou ausente")
        return destination

    @staticmethod
    def _mesh_metadata(result: Any, request_payload: dict[str, Any]) -> dict[str, Any]:
        metadata: dict[str, Any] = {}
        if isinstance(result, dict) and isinstance(result.get("data"), (list, tuple)):
            result = result["data"]
        stats = (
            result[2] if isinstance(result, (list, tuple)) and len(result) > 2 else None
        )
        aliases = {
            "number_of_faces": ("number_of_faces", "faces", "num_faces"),
            "number_of_vertices": (
                "number_of_vertices",
                "vertices",
                "num_vertices",
            ),
            "total_time": ("total_time", "generation_time", "time"),
            "steps": ("steps",),
            "guidance_scale": ("guidance_scale", "guidance"),
            "seed": ("seed",),
            "octree_resolution": ("octree_resolution", "octree"),
        }
        if isinstance(stats, dict):
            for target, sources in aliases.items():
                for source in sources:
                    if source in stats and isinstance(stats[source], (int, float, str)):
                        metadata[target] = stats[source]
                        break
        for key in ("steps", "guidance_scale", "seed", "octree_resolution"):
            if key not in metadata and key in request_payload:
                metadata[key] = request_payload[key]
        if isinstance(result, (list, tuple)) and len(result) > 3:
            if isinstance(result[3], (int, float, str)):
                metadata["seed"] = result[3]
        return metadata

    def available(self) -> bool:
        return self.client.available(self.settings.health_timeout_seconds)

    def health(self) -> EngineHealth:
        available = self.client.available(self.settings.health_timeout_seconds)
        diagnostics = self.client.diagnostics()
        return EngineHealth(
            name=self.name,
            available=available,
            details={
                "configured": True,
                "url": self.settings.hunyuan_url,
                "api_name": self.settings.hunyuan_endpoint,
                **diagnostics,
            },
        )

    def generate(self, job_context: JobContext, input_image: Path) -> GenerationResult:
        job_id = job_context.job_id
        job_dir = job_context.job_dir
        started = time.monotonic()
        if self.gpu_lock is not None and self.process_manager is not None:
            with self.gpu_lock:
                self.process_manager.ensure_shape_running()
                response = self.client.generate(
                    input_image, self.settings.generation_timeout_seconds
                )
        else:
            response = self.client.generate(
                input_image, self.settings.generation_timeout_seconds
            )
        raw_result = response.data
        origin, source, original_name = self._artifact_from_result(raw_result)
        artifact = self._materialize(origin, source, original_name, job_dir)
        duration = time.monotonic() - started
        safe_mesh_metadata = self._mesh_metadata(raw_result, response.request_payload)
        return GenerationResult(
            job_id=job_id,
            engine=self.name,
            artifact_path=artifact,
            artifact_relative_path=artifact.name,
            metadata={
                "result_type": type(raw_result).__name__,
                "extension": artifact.suffix.lower(),
                "size_bytes": artifact.stat().st_size,
                "engine": self.name,
                "duration_seconds": round(duration, 3),
                "origin": origin,
                **safe_mesh_metadata,
            },
        )
