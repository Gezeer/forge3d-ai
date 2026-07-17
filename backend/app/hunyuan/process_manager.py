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
    ppid: Optional[int] = None
    pgid: Optional[int] = None
    sid: Optional[int] = None


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
            stat_fields = (entry / "stat").read_text().rsplit(") ", 1)[1].split()
            if argv:
                found.append(
                    ProcessInfo(
                        int(entry.name),
                        argv,
                        cwd,
                        ppid=int(stat_fields[1]),
                        pgid=int(stat_fields[2]),
                        sid=int(stat_fields[3]),
                    )
                )
        except (
            FileNotFoundError,
            PermissionError,
            ProcessLookupError,
            OSError,
            IndexError,
            ValueError,
        ):
            continue
    return found


class HunyuanProcessManager:
    def __init__(
        self,
        *,
        root: Path,
        python: Path,
        port: int = 8080,
        expected_endpoint: str = "/run/shape_generation",
        cache_path: Path = Path("/tmp/hunyuan-cache"),
        start_timeout: float = 300.0,
        stop_timeout: float = 30.0,
        log_path: Path = Path("/tmp/hunyuan-shape.log"),
        process_provider: Callable[[], Iterable[ProcessInfo]] = linux_processes,
        signaler: Callable[[int, int], None] = os.kill,
        group_signaler: Callable[[int, int], None] = os.killpg,
        getpgid: Callable[[int], int] = os.getpgid,
        getsid: Callable[[int], int] = os.getsid,
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
        self.expected_endpoint = (
            expected_endpoint
            if expected_endpoint.startswith("/")
            else f"/{expected_endpoint}"
        )
        self.cache_path = cache_path.expanduser()
        self.start_timeout = start_timeout
        self.stop_timeout = stop_timeout
        self.log_path = log_path.expanduser()
        self.process_provider = process_provider
        self.signaler = signaler
        self.group_signaler = group_signaler
        self.getpgid = getpgid
        self.getsid = getsid
        self.popen = popen
        self.ready_probe = ready_probe or self._http_ready
        self.port_probe = port_probe or self._port_open
        self.sleeper = sleeper
        self.monotonic = monotonic
        self._state = "unknown"
        self._state_lock = threading.Lock()
        self._managed_pid: Optional[int] = None
        self._managed_process: Optional[Any] = None
        self._managed_pgid: Optional[int] = None
        self._managed_sid: Optional[int] = None

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

    @property
    def readiness_urls(self) -> tuple[str, ...]:
        base = f"http://127.0.0.1:{self.port}"
        # Current Gradio API schema and the FastAPI schema used by older
        # Hunyuan/Gradio checkouts.  The HTML root is liveness, not readiness.
        return (
            f"{base}/gradio_api/openapi.json",
            f"{base}/openapi.json",
        )

    @staticmethod
    def _http_ready(url: str, timeout: float) -> httpx.Response:
        # Local health probes must never be routed through HTTP(S)_PROXY.
        with httpx.Client(follow_redirects=True, trust_env=False) as client:
            return client.get(url, timeout=timeout)

    def _response_is_ready(self, url: str, result: Any) -> bool:
        status_code = getattr(result, "status_code", None)
        if status_code is None:
            return bool(result)
        if int(status_code) != 200:
            return False
        if not url.endswith("openapi.json"):
            return False
        try:
            payload = result.json()
        except (AttributeError, ValueError):
            return False
        paths = payload.get("paths") if isinstance(payload, dict) else None
        return isinstance(paths, dict) and self.expected_endpoint in paths

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
            if callable(poll):
                # Popen.poll() is authoritative for a process we created.  Do not
                # introduce a race by requiring the same PID to also appear in a
                # separate /proc snapshot immediately after Popen returned.
                if poll() is None:
                    return True
                return self._managed_group_alive()
        return any(item.pid == pid for item in self.process_provider())

    def _managed_group_alive(self) -> bool:
        if self._managed_pgid is None:
            return False
        return any(
            item.pgid == self._managed_pgid for item in self.process_provider()
        )

    def _process_tree(self) -> list[dict[str, Any]]:
        processes = list(self.process_provider())
        if self._managed_pgid is not None:
            processes = [item for item in processes if item.pgid == self._managed_pgid]
        elif self._managed_pid is not None:
            processes = [item for item in processes if item.pid == self._managed_pid]
        return [
            {
                "pid": item.pid,
                "ppid": item.ppid,
                "pgid": item.pgid,
                "sid": item.sid,
                "argv": list(item.argv),
            }
            for item in processes
        ]

    def _signal_managed(self, sent: int) -> None:
        if self._managed_pgid is not None:
            self.group_signaler(self._managed_pgid, sent)
        elif self._managed_pid is not None:
            self.signaler(self._managed_pid, sent)

    def _process_returncode(self) -> Optional[int]:
        poll = getattr(self._managed_process, "poll", None)
        return poll() if callable(poll) else None

    def _log_tail(self, limit: int = 8192) -> str:
        try:
            with self.log_path.open("rb") as stream:
                stream.seek(0, os.SEEK_END)
                size = stream.tell()
                stream.seek(max(0, size - limit))
                return stream.read().decode(errors="replace")
        except OSError as error:
            return f"<unable to read process log: {error}>"

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
        if process is None and self._managed_group_alive():
            process = next(
                (
                    item
                    for item in self.process_provider()
                    if item.pgid == self._managed_pgid
                ),
                None,
            )
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
        managed_group = (
            self._managed_pgid is not None and process.pgid == self._managed_pgid
        )
        if managed_group:
            self._signal_managed(signal.SIGTERM)
        else:
            self.signaler(process.pid, signal.SIGTERM)
        try:
            self.wait_until_stopped(process.pid)
        except HunyuanProcessError:
            if self._process_exists(process.pid):
                if managed_group:
                    self._signal_managed(signal.SIGKILL)
                else:
                    self.signaler(process.pid, signal.SIGKILL)
            self.wait_until_stopped(process.pid, min(5.0, self.stop_timeout))
        duration = self.monotonic() - started
        logger.info(
            "hunyuan_shape_stopped pid=%s duration=%.3f",
            process.pid,
            duration,
            extra={"pid": process.pid, "duration_seconds": round(duration, 3)},
        )
        self._managed_process = None
        self._managed_pid = None
        self._managed_pgid = None
        self._managed_sid = None
        return process.pid

    def wait_until_ready(self, timeout: Optional[float] = None) -> None:
        started = self.monotonic()
        deadline = self.monotonic() + (
            self.start_timeout if timeout is None else timeout
        )
        last_exception: Optional[Exception] = None
        last_url: Optional[str] = None
        last_status: Optional[int] = None
        attempt = 0
        while self.monotonic() < deadline:
            if self._managed_pid is not None and not self._process_exists(self._managed_pid):
                returncode = self._process_returncode()
                duration = self.monotonic() - started
                output = self._log_tail()
                self._set_state("restart_failed")
                logger.error(
                    "Shape process exited before becoming healthy pid=%s "
                    "returncode=%s duration=%.3f stdout_stderr=%r",
                    self._managed_pid,
                    returncode,
                    duration,
                    output,
                    extra={
                        "pid": self._managed_pid,
                        "returncode": returncode,
                        "duration_seconds": round(duration, 3),
                        "stdout_stderr": output,
                        "process_tree": self._process_tree(),
                    },
                )
                raise HunyuanProcessError(
                    "Shape process exited before becoming healthy "
                    f"(returncode={returncode})"
                )
            for url in self.readiness_urls:
                if self.monotonic() >= deadline:
                    break
                last_url = url
                attempt += 1
                request_started = self.monotonic()
                try:
                    result = self.ready_probe(
                        url,
                        min(5.0, max(0.1, deadline - self.monotonic())),
                    )
                    status_code = getattr(result, "status_code", None)
                    last_status = int(status_code) if status_code is not None else None
                    healthy = self._response_is_ready(url, result)
                    response_text = getattr(result, "text", "")
                    process_alive = (
                        self._managed_pid is None
                        or self._process_exists(self._managed_pid)
                    )
                    port_open = self.port_probe("127.0.0.1", self.port, 0.2)
                    logger.info(
                        "hunyuan_shape_health_response attempt=%s url=%s status=%s "
                        "healthy=%s duration=%.3f process_alive=%s pid=%s pgid=%s "
                        "port_open=%s response=%r",
                        attempt,
                        url,
                        last_status,
                        healthy,
                        self.monotonic() - request_started,
                        process_alive,
                        self._managed_pid,
                        self._managed_pgid,
                        port_open,
                        str(response_text)[:1000],
                        extra={
                            "url": url,
                            "status_code": last_status,
                            "healthy": healthy,
                            "attempt": attempt,
                            "duration_seconds": round(
                                self.monotonic() - request_started, 3
                            ),
                        },
                    )
                    if healthy:
                        self._set_state("running")
                        logger.info(
                            "hunyuan_shape_ready pid=%s pgid=%s endpoint=%s "
                            "duration=%.3f",
                            self._managed_pid,
                            self._managed_pgid,
                            url,
                            self.monotonic() - started,
                        )
                        return
                except Exception as error:
                    last_exception = error
                    logger.warning(
                        "hunyuan_shape_health_exception attempt=%s url=%s "
                        "duration=%.3f pid=%s pgid=%s port_open=%s exception=%r",
                        attempt,
                        url,
                        self.monotonic() - request_started,
                        self._managed_pid,
                        self._managed_pgid,
                        self.port_probe("127.0.0.1", self.port, 0.2),
                        error,
                        extra={"url": url, "exception": repr(error)},
                    )
            self.sleeper(0.5)
        self._set_state("restart_failed")
        returncode = self._process_returncode()
        duration = self.monotonic() - started
        output = self._log_tail()
        exception_info = (
            (type(last_exception), last_exception, last_exception.__traceback__)
            if last_exception is not None
            else None
        )
        logger.error(
            "hunyuan_shape_health_failed url=%s status=%s duration=%.3f "
            "returncode=%s exception=%r stdout_stderr=%r log=%s",
            last_url,
            last_status,
            duration,
            returncode,
            last_exception,
            output,
            self.log_path,
            extra={
                "url": last_url,
                "status_code": last_status,
                "duration_seconds": round(duration, 3),
                "returncode": returncode,
                "exception": repr(last_exception),
                "stdout_stderr": output,
                "log_path": str(self.log_path),
                "process_tree": self._process_tree(),
            },
            exc_info=exception_info,
        )
        error = HunyuanProcessError("Hunyuan Shape não ficou pronto dentro do timeout")
        if last_exception is not None:
            raise error from last_exception
        raise error

    def start_shape_server(self) -> int:
        started = self.monotonic()
        existing = self.find_shape_process()
        if existing is not None:
            self._managed_pid = existing.pid
            self._managed_pgid = existing.pgid
            self._managed_sid = existing.sid
            self._managed_process = None
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
            "hunyuan_shape_starting port=%s command=%r cwd=%s environment=%r "
            "stdout=%s stderr=%s",
            self.port,
            command,
            self.root,
            relevant_environment,
            self.log_path,
            self.log_path,
            extra={
                "port": self.port,
                "command": command,
                "cwd": str(self.root),
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
            self._managed_pgid = self.getpgid(self._managed_pid)
            self._managed_sid = self.getsid(self._managed_pid)
        except OSError as error:
            self._managed_pgid = None
            self._managed_sid = None
            logger.warning(
                "hunyuan_shape_identity_unavailable pid=%s exception=%r",
                self._managed_pid,
                error,
            )
        logger.info(
            "hunyuan_shape_spawned pid=%s pgid=%s sid=%s command=%r cwd=%s "
            "started_at=%.6f",
            self._managed_pid,
            self._managed_pgid,
            self._managed_sid,
            command,
            self.root,
            started,
            extra={
                "pid": self._managed_pid,
                "pgid": self._managed_pgid,
                "sid": self._managed_sid,
                "command": command,
                "cwd": str(self.root),
            },
        )
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
                    self._signal_managed(signal.SIGTERM)
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
