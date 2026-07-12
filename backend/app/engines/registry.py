from __future__ import annotations

from typing import Dict, List

from app.core.exceptions import EngineAlreadyRegisteredError, EngineNotFoundError
from app.engines.contracts import Engine


class EngineRegistry:
    def __init__(self) -> None:
        self._engines: Dict[str, Engine] = {}

    @staticmethod
    def _normalize(name: str) -> str:
        return name.strip().lower()

    def register(self, engine: Engine) -> None:
        name = self._normalize(engine.name)
        if not name:
            raise ValueError("Engine name cannot be empty")
        if name in self._engines:
            raise EngineAlreadyRegisteredError(
                f"Engine '{name}' já está registrada"
            )
        self._engines[name] = engine

    def get(self, name: str) -> Engine:
        normalized = self._normalize(name)
        try:
            return self._engines[normalized]
        except KeyError as exc:
            raise EngineNotFoundError(
                f"Engine '{normalized}' não encontrada"
            ) from exc

    def list(self) -> List[Engine]:
        return list(self._engines.values())

    def available(self) -> List[Engine]:
        return [engine for engine in self._engines.values() if engine.available()]
