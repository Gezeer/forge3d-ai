from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol
from uuid import UUID

from app.engines.contracts import JobContext


@dataclass(frozen=True)
class TextureRequest:
    resolution: int
    quality: str


@dataclass(frozen=True)
class TextureResult:
    job_id: UUID
    status: str
    input_mesh: Path
    artifact_path: Path
    artifact_relative_path: str
    format: str
    metadata: dict[str, Any] = field(default_factory=dict)


class TextureService(Protocol):
    name: str

    def available(self) -> bool: ...

    def texture(
        self,
        job_context: JobContext,
        mesh_path: Path,
        reference_image: Path,
        request: TextureRequest,
    ) -> TextureResult: ...
