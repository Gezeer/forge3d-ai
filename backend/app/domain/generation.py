from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict
from uuid import UUID


@dataclass(frozen=True)
class GenerationResult:
    job_id: UUID
    engine: str
    artifact_path: Path
    artifact_relative_path: str
    metadata: Dict[str, Any] = field(default_factory=dict)
