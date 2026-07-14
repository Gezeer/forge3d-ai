from __future__ import annotations

import signal
from pathlib import Path
from types import SimpleNamespace

import pytest
from app.hunyuan.process_manager import (
    HunyuanProcessError,
    HunyuanProcessManager,
    ProcessInfo,
)


class Clock:
    def __init__(self):
        self.value = 0.0

    def monotonic(self):
        return self.value

    def sleep(self, seconds):
        self.value += seconds


class Runtime:
    def __init__(self, root: Path, python: Path):
        self.root = root.resolve()
        self.python = python.resolve()
        self.processes = []
        self.signals = []
        self.popen_calls = []
        self.ready_values = [True]
        self.ready_urls = []
        self.remove_on_term = True
        self.next_pid = 9001

    def correct(self, pid=123):
        return ProcessInfo(
            pid,
            (
                str(self.python),
                "gradio_app.py",
                "--host",
                "0.0.0.0",
                "--port",
                "8080",
            ),
            self.root,
        )

    def provider(self):
        return list(self.processes)

    def signaler(self, pid, sent):
        self.signals.append((pid, sent))
        if sent == signal.SIGKILL or self.remove_on_term:
            self.processes = [item for item in self.processes if item.pid != pid]

    def port_probe(self, host, port, timeout):
        return any(item.pid for item in self.processes)

    def popen(self, command, **kwargs):
        self.popen_calls.append((command, kwargs))
        process = ProcessInfo(self.next_pid, tuple(command), self.root)
        self.processes.append(process)
        return SimpleNamespace(pid=self.next_pid)

    def ready_probe(self, url, timeout):
        self.ready_urls.append(url)
        if len(self.ready_values) > 1:
            return self.ready_values.pop(0)
        return self.ready_values[0]


def manager(tmp_path: Path, runtime: Runtime, clock: Clock | None = None):
    clock = clock or Clock()
    return HunyuanProcessManager(
        root=runtime.root,
        python=runtime.python,
        port=8080,
        cache_path=tmp_path / "cache",
        start_timeout=1,
        stop_timeout=0.4,
        log_path=tmp_path / "shape.log",
        process_provider=runtime.provider,
        signaler=runtime.signaler,
        popen=runtime.popen,
        ready_probe=runtime.ready_probe,
        port_probe=runtime.port_probe,
        sleeper=clock.sleep,
        monotonic=clock.monotonic,
    )


def setup_runtime(tmp_path: Path):
    root = tmp_path / "Hunyuan3D-2.1"
    root.mkdir()
    (root / "gradio_app.py").write_text("# fixture", encoding="utf-8")
    python = tmp_path / "venv" / "bin" / "python"
    python.parent.mkdir(parents=True)
    python.write_text("", encoding="utf-8")
    return Runtime(root, python)


def test_find_shape_process_requires_script_port_python_and_root(tmp_path: Path):
    runtime = setup_runtime(tmp_path)
    correct = runtime.correct()
    runtime.processes = [
        ProcessInfo(1, (str(runtime.python), "api.py", "--port", "8080"), runtime.root),
        ProcessInfo(
            2, ("/usr/bin/python", "gradio_app.py", "--port", "8080"), runtime.root
        ),
        ProcessInfo(
            3, (str(runtime.python), "gradio_app.py", "--port", "9999"), runtime.root
        ),
        ProcessInfo(4, correct.argv, tmp_path / "other"),
        correct,
    ]

    found = manager(tmp_path, runtime).find_shape_process()

    assert found == correct


def test_stop_never_signals_wrong_process_on_managed_port(tmp_path: Path):
    runtime = setup_runtime(tmp_path)
    runtime.processes = [
        ProcessInfo(77, ("/usr/bin/python", "other.py", "--port", "8080"), runtime.root)
    ]

    with pytest.raises(HunyuanProcessError, match="não gerenciado"):
        manager(tmp_path, runtime).stop_shape_server()

    assert runtime.signals == []


def test_stop_uses_sigterm_and_confirms_process_and_port_stopped(tmp_path: Path):
    runtime = setup_runtime(tmp_path)
    runtime.processes = [runtime.correct(321)]

    stopped = manager(tmp_path, runtime).stop_shape_server()

    assert stopped == 321
    assert runtime.signals == [(321, signal.SIGTERM)]
    assert runtime.processes == []


def test_stop_falls_back_to_sigkill_after_timeout(tmp_path: Path):
    runtime = setup_runtime(tmp_path)
    runtime.remove_on_term = False
    runtime.processes = [runtime.correct(654)]

    manager(tmp_path, runtime).stop_shape_server()

    assert runtime.signals == [(654, signal.SIGTERM), (654, signal.SIGKILL)]


def test_start_does_not_duplicate_existing_shape(tmp_path: Path):
    runtime = setup_runtime(tmp_path)
    runtime.processes = [runtime.correct(555)]

    pid = manager(tmp_path, runtime).start_shape_server()

    assert pid == 555
    assert runtime.popen_calls == []


def test_start_uses_exact_command_and_waits_for_openapi(tmp_path: Path):
    runtime = setup_runtime(tmp_path)
    runtime.ready_values = [False, True]
    process_manager = manager(tmp_path, runtime)

    pid = process_manager.start_shape_server()

    assert pid == runtime.next_pid
    command, options = runtime.popen_calls[0]
    assert command == [
        str(runtime.python),
        "gradio_app.py",
        "--host",
        "0.0.0.0",
        "--port",
        "8080",
        "--cache-path",
        str(tmp_path / "cache"),
    ]
    assert options["cwd"] == str(runtime.root)
    assert options["start_new_session"] is True
    assert runtime.ready_urls[-1].endswith("/gradio_api/openapi.json")
    assert process_manager.operational_state == "running"


def test_start_timeout_is_safe_and_marks_restart_failed(tmp_path: Path):
    runtime = setup_runtime(tmp_path)
    runtime.ready_values = [False]
    process_manager = manager(tmp_path, runtime)

    with pytest.raises(HunyuanProcessError, match="não ficou pronto"):
        process_manager.start_shape_server()

    assert process_manager.operational_state == "restart_failed"
    assert runtime.signals[-1] == (runtime.next_pid, signal.SIGTERM)
