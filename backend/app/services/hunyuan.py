from __future__ import annotations

import json
import shutil
import time
from pathlib import Path
from typing import Any, Iterator, Optional
from urllib.parse import unquote, urlparse

from app.core.config import Settings
from app.core.exceptions import ArtifactNotFoundError, ServiceUnavailableError
from app.domain.generation import GenerationResult
from app.engines.contracts import EngineHealth, JobContext
from app.infrastructure.hunyuan_gateway import HunyuanGateway, HunyuanSignature
from app.infrastructure.storage import LocalStorage


class HunyuanService:
    name = "hunyuan"
    supported_artifacts = {".glb", ".obj", ".ply", ".stl"}

    def __init__(
        self,
        settings: Settings,
        storage: LocalStorage,
        gateway: HunyuanGateway,
        signature: Optional[HunyuanSignature] = None,
        downloader=None,
    ) -> None:
        self.settings = settings
        self.storage = storage
        self.gateway = gateway
        self.signature = signature or self._signature_from_settings()
        self.downloader = downloader or self._download

    def _signature_from_settings(self) -> Optional[HunyuanSignature]:
        if not self.settings.hunyuan_signature_json.strip():
            return None
        try:
            payload = json.loads(self.settings.hunyuan_signature_json)
            args = payload.get("args", [])
            kwargs = payload.get("kwargs", {})
            if not isinstance(args, list) or not isinstance(kwargs, dict):
                raise ValueError
        except (json.JSONDecodeError, AttributeError, ValueError) as exc:
            raise ServiceUnavailableError(
                "A assinatura configurada do Hunyuan é inválida"
            ) from exc
        return HunyuanSignature(args=args, kwargs=kwargs)

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
        destination = job_dir / safe_name
        if destination.exists():
            destination = job_dir / f"hunyuan_model{suffix}"
        if kind == "remote":
            self.downloader(source, destination)
        else:
            local_source = Path(source)
            if local_source.resolve() != destination.resolve():
                shutil.copy2(local_source, destination)
        if not destination.is_file() or destination.stat().st_size <= 0:
            raise ArtifactNotFoundError("Artefato Hunyuan vazio ou ausente")
        return destination

    def available(self) -> bool:
        return self.signature is not None and self.gateway.available()

    def health(self) -> EngineHealth:
        configured = self.signature is not None
        available = configured and self.gateway.available()
        return EngineHealth(
            name=self.name,
            available=available,
            details={
                "configured": configured,
                "url": self.settings.hunyuan_url,
                "api_name": self.settings.hunyuan_api_name,
            },
        )

    def generate(self, job_context: JobContext, input_image: Path) -> GenerationResult:
        job_id = job_context.job_id
        job_dir = job_context.job_dir
        if self.signature is None:
            raise ServiceUnavailableError(
                "Assinatura Hunyuan não configurada; inspecione a API no RunPod"
            )
        started = time.monotonic()
        raw_result = self.gateway.predict(
            input_image,
            self.signature,
            self.settings.hunyuan_api_name,
            self.settings.generation_timeout_seconds,
        )
        origin, source, original_name = self._artifact_from_result(raw_result)
        artifact = self._materialize(origin, source, original_name, job_dir)
        duration = time.monotonic() - started
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
            },
        )
