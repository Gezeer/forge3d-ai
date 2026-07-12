from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, Optional
from uuid import UUID

from app.core.config import Settings
from app.core.exceptions import ArtifactNotFoundError, ServiceUnavailableError
from app.domain.generation import GenerationResult
from app.infrastructure.hunyuan_gateway import HunyuanGateway, HunyuanSignature
from app.infrastructure.storage import LocalStorage


class HunyuanService:
    engine = "hunyuan"
    supported_artifacts = {".glb", ".gltf", ".obj", ".ply", ".stl", ".zip"}

    def __init__(
        self,
        settings: Settings,
        storage: LocalStorage,
        gateway: HunyuanGateway,
        signature: Optional[HunyuanSignature] = None,
    ) -> None:
        self.settings = settings
        self.storage = storage
        self.gateway = gateway
        self.signature = signature or self._signature_from_settings()

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

    def _artifact_from_result(self, result: Any) -> Path:
        for value in self._values(result):
            if isinstance(value, Path):
                candidate = value
            elif isinstance(value, str):
                candidate = Path(value)
            else:
                continue
            if (
                candidate.suffix.lower() in self.supported_artifacts
                and candidate.is_file()
            ):
                return candidate
        raise ArtifactNotFoundError(
            "O Hunyuan respondeu, mas nenhum artefato 3D local foi encontrado"
        )

    def generate(
        self, job_id: UUID, input_image: Path, job_dir: Path
    ) -> GenerationResult:
        if self.signature is None:
            raise ServiceUnavailableError(
                "Assinatura Hunyuan não configurada; inspecione a API no RunPod"
            )
        raw_result = self.gateway.predict(
            input_image,
            self.signature,
            self.settings.hunyuan_api_name,
            self.settings.generation_timeout_seconds,
        )
        source = self._artifact_from_result(raw_result)
        artifact_dir = job_dir / "hunyuan"
        artifact_dir.mkdir(parents=True, exist_ok=True)
        artifact = self.storage.copy_artifact(
            source, artifact_dir, f"model{source.suffix.lower()}"
        )
        return GenerationResult(
            job_id=job_id,
            engine=self.engine,
            artifact_path=artifact,
            artifact_relative_path=f"hunyuan/{artifact.name}",
            metadata={"result_type": type(raw_result).__name__},
        )
