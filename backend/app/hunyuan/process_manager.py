from __future__ import annotations

import logging
import os
import signal
import socket
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Optional

import httpx

logger = logging.getLogger("forge3d.hunyuan.process")

RELEVANT_ENVIRONMENT_VARIABLES = (
    "HF_HOME",
    "HUGGINGFACE_HUB_CACHE",
    "TRANSFORMERS_CACHE",
    "TMPDIR",
    "NUMBA_CACHE_DIR",
    "TORCH_HOME",
    "XDG_CACHE_HOME",
    "MPLCONFIGDIR",
    "FORGE3D_TEXTURE_CACHE",
    "FORGE3D_UPLOAD_DIR",
    "FORGE3D_OUTPUT_DIR",
)


class HunyuanProcessError(RuntimeError):
    """Safe operational error from the managed Shape process."""


@dataclass(frozen=True)
class ProcessInfo:
    pid: int
    argv: tuple[str, ...]
    cwd: Optional[Path]


def linux_processes() -> Iterable[ProcessInfo]:
    proc = Path("/proc")
    if not proc.is_dir():
        return []
    found = []
    for entry in proc.iterdir():
        if not entry.name.isdigit():
            continue
        try:
            raw = (entry / "cmdline").read_bytes()
            argv = tuple(
                part.decode(errors="replace") for part in raw.split(b"\0") if part
            )
            cwd = (entry / "cwd").resolve()
            if argv:
                found.append(ProcessInfo(int(entry.name), argv, cwd))
        except (FileNotFoundError, PermissionError, ProcessLookupError, OSError):
            continue
    return found


class HunyuanProcessManager:
    def __init__(
        self,
        *,
        root: Path,
        python: Path,
        port: int = 8080,
        cache_path: Path = Path("/tmp/hunyuan-cache"),
        start_timeout: float = 300.0,
        stop_timeout: float = 30.0,
        log_path: Path = Path("/tmp/hunyuan-shape.log"),
        process_provider: Callable[[], Iterable[ProcessInfo]] = linux_processes,
        signaler: Callable[[int, int], None] = os.kill,
        popen: Callable[..., Any] = subprocess.Popen,
        ready_probe: Optional[Callable[[str, float], Any]] = None,
        port_probe: Optional[Callable[[str, int, float], bool]] = None,
        sleeper: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self.root = root.expanduser().resolve()
        self.python = python.expanduser().absolute()
        self._python_resolved = self.python.resolve()
        self.port = port
        self.cache_path = cache_path.expanduser()
        self.start_timeout = start_timeout
        self.stop_timeout = stop_timeout
        self.log_path = log_path.expanduser()
        self.process_provider = process_provider
        self.signaler = signaler
        self.popen = popen
        self.ready_probe = ready_probe or self._http_ready
        self.port_probe = port_probe or self._port_open
        self.sleeper = sleeper
        self.monotonic = monotonic
        self._state = "unknown"
        self._state_lock = threading.Lock()
        self._managed_pid: Optional[int] = None
        self._managed_process: Optional[Any] = None

    @property
    def operational_state(self) -> str:
        with self._state_lock:
            return self._state

    def _set_state(self, state: str) -> None:
        with self._state_lock:
            self._state = state

    @property
    def openapi_url(self) -> str:
        return f"http://127.0.0.1:{self.port}/gradio_api/openapi.json"

    @staticmethod
    def _http_ready(url: str, timeout: float) -> bool:
        response = httpx.get(url, timeout=timeout, follow_redirects=True)
        return response.status_code == 200

    @staticmethod
    def _port_open(host: str, port: int, timeout: float) -> bool:
        try:
            with socket.create_connection((host, port), timeout=timeout):
                return True
        except OSError:
            return False

    def _matches(self, process: ProcessInfo) -> bool:
        if not process.argv or process.cwd is None:
            return False
        try:
            executable_matches = (
                Path(process.argv[0]).resolve() == self._python_resolved
            )
            cwd_matches = process.cwd.resolve() == self.root
        except OSError:
            return False
        script_matches = any(Path(arg).name == "gradio_app.py" for arg in process.argv)
        port_matches = any(
            (
                arg == "--port"
                and index + 1 < len(process.argv)
                and process.argv[index + 1] == str(self.port)
            )
            or arg == f"--port={self.port}"
            for index, arg in enumerate(process.argv)
        )
        return executable_matches and cwd_matches and script_matches and port_matches

    def find_shape_process(self) -> Optional[ProcessInfo]:
        return next(
            (item for item in self.process_provider() if self._matches(item)), None
        )

    def is_shape_running(self) -> bool:
        return self.find_shape_process() is not None

    def _process_exists(self, pid: int) -> bool:
        if self._managed_pid == pid and self._managed_process is not None:
            poll = getattr(self._managed_process, "poll", None)
            if callable(poll) and poll() is not None:
                return False
        return any(item.pid == pid for item in self.process_provider())

    def wait_until_stopped(self, pid: int, timeout: Optional[float] = None) -> None:
        deadline = self.monotonic() + (
            self.stop_timeout if timeout is None else timeout
        )
        while self.monotonic() < deadline:
            process_gone = not self._process_exists(pid)
            port_released = not self.port_probe("127.0.0.1", self.port, 0.5)
            if process_gone and port_released:
                return
            self.sleeper(0.2)
        raise HunyuanProcessError("Hunyuan Shape não encerrou dentro do timeout")

    def stop_shape_server(self) -> Optional[int]:
        started = self.monotonic()
        process = self.find_shape_process()
        if process is None:
            if self.port_probe("127.0.0.1", self.port, 0.5):
                raise HunyuanProcessError(
                    f"Porta {self.port} ocupada por processo não gerenciado"
                )
            self._set_state("paused_for_texture")
            return None
        self._set_state("paused_for_texture")
        logger.info(
            "hunyuan_shape_stopping pid=%s", process.pid, extra={"pid": process.pid}
        )
        self.signaler(process.pid, signal.SIGTERM)
        try:
            self.wait_until_stopped(process.pid)
        except HunyuanProcessError:
            if self._process_exists(process.pid):
                self.signaler(process.pid, signal.SIGKILL)
            self.wait_until_stopped(process.pid, min(5.0, self.stop_timeout))
        duration = self.monotonic() - started
        logger.info(
            "hunyuan_shape_stopped pid=%s duration=%.3f",
            process.pid,
            duration,
            extra={"pid": process.pid, "duration_seconds": round(duration, 3)},
        )
        if self._managed_pid == process.pid:
            self._managed_process = None
        return process.pid

    def wait_until_ready(self, timeout: Optional[float] = None) -> None:
        started = self.monotonic()
        deadline = self.monotonic() + (
            self.start_timeout if timeout is None else timeout
        )
        last_exception: Optional[Exception] = None
        while self.monotonic() < deadline:
            try:
                if bool(
                    self.ready_probe(
                        self.openapi_url,
                        min(5.0, max(0.1, deadline - self.monotonic())),
                    )
                ):
                    self._set_state("running")
                    return
            except Exception as error:
                last_exception = error
            if self._managed_pid is not None and not self._process_exists(
                self._managed_pid
            ):
                break
            self.sleeper(0.5)
        self._set_state("restart_failed")
        process = self._managed_process
        poll = getattr(process, "poll", None)
        returncode = poll() if callable(poll) else None
        duration = self.monotonic() - started
        logger.error(
            "hunyuan_shape_health_failed url=%s duration=%.3f returncode=%s "
            "exception=%r stdout=%s stderr=%s",
            self.openapi_url,
            duration,
            returncode,
            last_exception,
            self.log_path,
            self.log_path,
            extra={
                "duration_seconds": round(duration, 3),
                "returncode": returncode,
                "exception": repr(last_exception),
                "stdout_path": str(self.log_path),
                "stderr_path": str(self.log_path),
            },
        )
        raise HunyuanProcessError("Hunyuan Shape não ficou pronto dentro do timeout")

    def start_shape_server(self) -> int:
        started = self.monotonic()
        existing = self.find_shape_process()
        if existing is not None:
            self._managed_pid = existing.pid
            self.wait_until_ready()
            return existing.pid
        if self.port_probe("127.0.0.1", self.port, 0.5):
            raise HunyuanProcessError(
                f"Porta {self.port} ocupada por processo não gerenciado"
            )
        script = self.root / "gradio_app.py"
        if not self.root.is_dir() or not script.is_file() or not self.python.is_file():
            raise HunyuanProcessError("Configuração do processo Hunyuan Shape inválida")
        self.cache_path.mkdir(parents=True, exist_ok=True)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        command = [
            str(self.python),
            "gradio_app.py",
            "--host",
            "0.0.0.0",
            "--port",
            str(self.port),
            "--cache-path",
            str(self.cache_path),
        ]
        environment = os.environ.copy()
        relevant_environment = {
            name: environment.get(name) for name in RELEVANT_ENVIRONMENT_VARIABLES
        }
        self._set_state("restarting")
        logger.info(
            "hunyuan_shape_starting port=%s command=%r environment=%r "
            "stdout=%s stderr=%s",
            self.port,
            command,
            relevant_environment,
            self.log_path,
            self.log_path,
            extra={
                "port": self.port,
                "command": command,
                "environment": relevant_environment,
                "stdout_path": str(self.log_path),
                "stderr_path": str(self.log_path),
            },
        )
        with self.log_path.open("ab") as log_stream:
            process = self.popen(
                command,
                cwd=str(self.root),
                env=environment,
                stdout=log_stream,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        self._managed_pid = int(process.pid)
        self._managed_process = process
        try:
            self.wait_until_ready()
        except Exception as error:
            poll = getattr(process, "poll", None)
            returncode = poll() if callable(poll) else None
            logger.exception(
                "hunyuan_shape_start_failed pid=%s returncode=%s exception=%r",
                self._managed_pid,
                returncode,
                error,
                extra={"pid": self._managed_pid, "returncode": returncode},
            )
            try:
                if self._process_exists(self._managed_pid):
                    self.signaler(self._managed_pid, signal.SIGTERM)
            except OSError:
                pass
            raise
        logger.info(
            "hunyuan_shape_ready pid=%s port=%s duration=%.3f returncode=%s",
            self._managed_pid,
            self.port,
            self.monotonic() - started,
            None,
            extra={
                "pid": self._managed_pid,
                "port": self.port,
                "duration_seconds": round(self.monotonic() - started, 3),
                "returncode": None,
            },
        )
        return self._managed_pid

    def ensure_shape_running(self) -> int:
        try:
            process = self.find_shape_process()
            if process is not None:
                self._managed_pid = process.pid
                self.wait_until_ready()
                return process.pid
            return self.start_shape_server()
        except Exception:
            self._set_state("restart_failed")
            raise
