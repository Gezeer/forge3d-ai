from __future__ import annotations

from app.core.exceptions import EngineUnavailableError
from app.engines.contracts import Engine
from app.engines.registry import EngineRegistry


class AutoEnginePolicy:
    def __init__(
        self,
        registry: EngineRegistry,
        preferred: str = "hunyuan",
        fallback: str = "triposr",
    ) -> None:
        self.registry = registry
        self.preferred = preferred
        self.fallback = fallback

    def select(self) -> Engine:
        preferred = self.registry.get(self.preferred)
        if preferred.available():
            return preferred
        fallback = self.registry.get(self.fallback)
        if fallback.available():
            return fallback
        raise EngineUnavailableError(
            "Nenhuma engine da política automática está disponível"
        )
