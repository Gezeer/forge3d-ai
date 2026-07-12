from pathlib import Path
from uuid import uuid4

import pytest

from app.core.exceptions import (
    EngineAlreadyRegisteredError,
    EngineNotFoundError,
    EngineUnavailableError,
)
from app.engines.contracts import EngineHealth, JobContext
from app.engines.policy import AutoEnginePolicy
from app.engines.registry import EngineRegistry


class FakeEngine:
    def __init__(self, name: str, is_available: bool = True) -> None:
        self.name = name
        self.is_available = is_available

    def available(self) -> bool:
        return self.is_available

    def health(self) -> EngineHealth:
        return EngineHealth(self.name, self.is_available, {})

    def generate(self, job_context: JobContext, image_path: Path):
        raise NotImplementedError


def test_registry_registers_finds_and_lists_engines() -> None:
    registry = EngineRegistry()
    triposr = FakeEngine("triposr")
    hunyuan = FakeEngine("hunyuan", is_available=False)

    registry.register(triposr)
    registry.register(hunyuan)

    assert registry.get(" TRIPOSR ") is triposr
    assert registry.list() == [triposr, hunyuan]
    assert registry.available() == [triposr]


def test_registry_rejects_duplicate_name() -> None:
    registry = EngineRegistry()
    registry.register(FakeEngine("triposr"))

    with pytest.raises(EngineAlreadyRegisteredError, match="já está registrada"):
        registry.register(FakeEngine("TRIPOSR"))


def test_registry_normalizes_missing_engine_error() -> None:
    registry = EngineRegistry()

    with pytest.raises(EngineNotFoundError, match="não encontrada"):
        registry.get("unknown")


def test_auto_policy_prefers_available_hunyuan() -> None:
    registry = EngineRegistry()
    triposr = FakeEngine("triposr")
    hunyuan = FakeEngine("hunyuan")
    registry.register(triposr)
    registry.register(hunyuan)

    assert AutoEnginePolicy(registry).select() is hunyuan


def test_auto_policy_falls_back_to_triposr() -> None:
    registry = EngineRegistry()
    triposr = FakeEngine("triposr")
    registry.register(triposr)
    registry.register(FakeEngine("hunyuan", is_available=False))

    assert AutoEnginePolicy(registry).select() is triposr


def test_auto_policy_fails_when_both_engines_are_unavailable() -> None:
    registry = EngineRegistry()
    registry.register(FakeEngine("triposr", is_available=False))
    registry.register(FakeEngine("hunyuan", is_available=False))

    with pytest.raises(EngineUnavailableError, match="Nenhuma engine"):
        AutoEnginePolicy(registry).select()
