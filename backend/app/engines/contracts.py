from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Protocol
from uuid import UUID

from app.domain.generation import GenerationResult


@dataclass(frozen=True)
class JobContext:
    job_id: UUID
    job_dir: Path


@dataclass(frozen=True)
class EngineHealth:
    name: str
    available: bool
    details: Dict[str, Any]


class Engine(Protocol):
    name: str

    def available(self) -> bool: ...

    def generate(
        self, job_context: JobContext, image_path: Path
    ) -> GenerationResult: ...

    def health(self) -> EngineHealth: ...
