from __future__ import annotations

import subprocess
from dataclasses import dataclass
from typing import Protocol, Sequence

from app.core.exceptions import GenerationError, GenerationTimeoutError


@dataclass(frozen=True)
class ProcessResult:
    returncode: int
    stdout: str = ""
    stderr: str = ""


class ProcessRunner(Protocol):
    def run(self, command: Sequence[str], timeout: float) -> ProcessResult:
        ...


class SubprocessRunner:
    def run(self, command: Sequence[str], timeout: float) -> ProcessResult:
        try:
            process = subprocess.run(
                list(command),
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise GenerationTimeoutError(
                "A geração excedeu o tempo limite configurado"
            ) from exc
        except OSError as exc:
            raise GenerationError("Não foi possível iniciar o gerador") from exc
        return ProcessResult(
            returncode=process.returncode,
            stdout=process.stdout,
            stderr=process.stderr,
        )
