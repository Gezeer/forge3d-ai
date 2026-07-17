from __future__ import annotations

import logging
import os
import signal
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import app.hunyuan.process_manager as process_manager_module
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
        self.returncode = None
        self.hide_processes = False
        self.spawn_child = False
        self.port_values = []

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
            pgid=pid,
            sid=pid,
        )

    def provider(self):
        if self.hide_processes:
            return []
        if self.returncode is not None and not self.spawn_child:
            return [item for item in self.processes if item.pid != self.next_pid]
        return list(self.processes)

    def signaler(self, pid, sent):
        self.signals.append((pid, sent))
        if sent == signal.SIGKILL or self.remove_on_term:
            self.processes = [item for item in self.processes if item.pid != pid]

    def port_probe(self, host, port, timeout):
        if self.port_values:
            return self.port_values.pop(0)
        return any(item.pid for item in self.processes)

    def popen(self, command, **kwargs):
        self.popen_calls.append((command, kwargs))
        if self.spawn_child:
            self.processes.append(
                ProcessInfo(
                    self.next_pid + 1,
                    (str(self.python), "uvicorn-child"),
                    self.root,
                    ppid=self.next_pid,
                    pgid=self.next_pid,
                    sid=self.next_pid,
                )
            )
        else:
            self.processes.append(
                ProcessInfo(
                    self.next_pid,
                    tuple(command),
                    self.root,
                    pgid=self.next_pid,
                    sid=self.next_pid,
                )
            )
        return SimpleNamespace(pid=self.next_pid, poll=lambda: self.returncode)

    def group_signaler(self, pgid, sent):
        self.signals.append((pgid, sent))
        self.processes = [item for item in self.processes if item.pgid != pgid]

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
        group_signaler=runtime.group_signaler,
        getpgid=lambda pid: pid,
        getsid=lambda pid: pid,
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


def test_start_uses_exact_command_and_falls_back_between_readiness_urls(tmp_path: Path):
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
    assert options["env"] == os.environ
    assert options["env"] is not os.environ
    assert options["start_new_session"] is True
    assert runtime.ready_urls == [
        "http://127.0.0.1:8080/gradio_api/openapi.json",
        "http://127.0.0.1:8080/openapi.json",
    ]
    assert process_manager.operational_state == "running"


def test_start_preserves_all_cache_and_runtime_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    runtime = setup_runtime(tmp_path)
    expected = {
        "HF_HOME": "/tmp/hf",
        "HUGGINGFACE_HUB_CACHE": "/tmp/hub",
        "TRANSFORMERS_CACHE": "/tmp/transformers",
        "TMPDIR": "/tmp/runtime",
        "NUMBA_CACHE_DIR": "/tmp/numba",
        "TORCH_HOME": "/tmp/torch",
        "XDG_CACHE_HOME": "/tmp/xdg",
        "MPLCONFIGDIR": "/tmp/matplotlib",
        "FORGE3D_TEXTURE_CACHE": "/tmp/texture",
        "FORGE3D_UPLOAD_DIR": "/tmp/uploads",
        "FORGE3D_OUTPUT_DIR": "/tmp/outputs",
    }
    for name, value in expected.items():
        monkeypatch.setenv(name, value)

    manager(tmp_path, runtime).start_shape_server()

    _, options = runtime.popen_calls[0]
    assert {name: options["env"][name] for name in expected} == expected


def test_start_timeout_is_safe_and_marks_restart_failed(tmp_path: Path):
    runtime = setup_runtime(tmp_path)
    runtime.ready_values = [False]
    process_manager = manager(tmp_path, runtime)

    with pytest.raises(HunyuanProcessError, match="não ficou pronto"):
        process_manager.start_shape_server()

    assert process_manager.operational_state == "restart_failed"
    assert runtime.signals[-1] == (runtime.next_pid, signal.SIGTERM)


class Response:
    def __init__(self, status_code: int, payload: Any = None, text: str = ""):
        self.status_code = status_code
        self.payload = payload
        self.text = text

    def json(self):
        if self.payload is None:
            raise ValueError("not json")
        return self.payload


def test_parent_can_exit_while_server_child_in_process_group_becomes_ready(
    tmp_path: Path,
):
    runtime = setup_runtime(tmp_path)
    runtime.returncode = 0
    runtime.spawn_child = True
    runtime.ready_values = [True]

    process_manager = manager(tmp_path, runtime)
    pid = process_manager.start_shape_server()

    assert pid == runtime.next_pid
    assert process_manager.operational_state == "running"
    assert process_manager._process_tree()[0]["pid"] == runtime.next_pid + 1


def test_open_port_does_not_count_as_ready_before_http_schema(tmp_path: Path):
    runtime = setup_runtime(tmp_path)
    runtime.ready_values = [
        Response(503, {"detail": "loading"}),
        Response(503, {"detail": "loading"}),
        Response(200, {"paths": {"/run/shape_generation": {}}}),
    ]

    process_manager = manager(tmp_path, runtime)
    process_manager.start_shape_server()

    assert len(runtime.ready_urls) == 3
    assert process_manager.operational_state == "running"


def test_primary_404_falls_back_to_legacy_openapi(tmp_path: Path):
    runtime = setup_runtime(tmp_path)
    runtime.ready_values = [
        Response(404, text="not found"),
        Response(200, {"paths": {"/run/shape_generation": {}}}),
    ]

    manager(tmp_path, runtime).start_shape_server()

    assert runtime.ready_urls[-1].endswith("/openapi.json")


def test_html_root_is_not_used_as_readiness(tmp_path: Path):
    runtime = setup_runtime(tmp_path)
    runtime.ready_values = [False, True]

    manager(tmp_path, runtime).start_shape_server()

    assert all(not url.endswith(":8080/") for url in runtime.ready_urls)


def test_local_http_probe_disables_environment_proxy(monkeypatch: pytest.MonkeyPatch):
    options = {}

    class Client:
        def __init__(self, **kwargs):
            options.update(kwargs)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def get(self, url, timeout):
            return Response(200, {"paths": {"/run/shape_generation": {}}})

    monkeypatch.setattr(process_manager_module.httpx, "Client", Client)

    response = HunyuanProcessManager._http_ready("http://127.0.0.1:8080", 1)

    assert response.status_code == 200
    assert options["trust_env"] is False


def test_stop_waits_until_port_is_released_before_returning(tmp_path: Path):
    runtime = setup_runtime(tmp_path)
    runtime.processes = [runtime.correct(321)]
    runtime.port_values = [True, True, False]
    clock = Clock()

    manager(tmp_path, runtime, clock).stop_shape_server()

    assert clock.value >= 0.4


def test_timeout_logs_process_port_tree_output_and_original_exception(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
):
    runtime = setup_runtime(tmp_path)
    runtime.ready_values = [RuntimeError("connection refused")]
    process_manager = manager(tmp_path, runtime)
    process_manager.ready_probe = lambda url, timeout: (_ for _ in ()).throw(
        RuntimeError("connection refused")
    )
    process_manager.log_path.write_text("shape diagnostic", encoding="utf-8")

    with caplog.at_level(logging.WARNING, logger="forge3d.hunyuan.process"):
        with pytest.raises(HunyuanProcessError, match="não ficou pronto") as caught:
            process_manager.start_shape_server()

    assert isinstance(caught.value.__cause__, RuntimeError)
    assert "connection refused" in caplog.text
    assert "shape diagnostic" in caplog.text


def test_simulated_stop_paint_restart_cycle_finishes_ready(tmp_path: Path):
    runtime = setup_runtime(tmp_path)
    runtime.processes = [runtime.correct(321)]
    process_manager = manager(tmp_path, runtime)

    process_manager.stop_shape_server()
    runtime.ready_values = [False, True]
    pid = process_manager.ensure_shape_running()

    assert pid == runtime.next_pid
    assert process_manager.operational_state == "running"


def test_managed_popen_poll_is_authoritative_when_proc_snapshot_misses_pid(
    tmp_path: Path
):
    runtime = setup_runtime(tmp_path)
    runtime.hide_processes = True
    runtime.ready_values = [False, False, True]

    process_manager = manager(tmp_path, runtime)
    pid = process_manager.start_shape_server()

    assert pid == runtime.next_pid
    assert process_manager.operational_state == "running"


def test_process_exit_before_health_is_explicit_and_logs_returncode(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
):
    runtime = setup_runtime(tmp_path)
    runtime.returncode = 17
    process_manager = manager(tmp_path, runtime)

    with caplog.at_level(logging.ERROR, logger="forge3d.hunyuan.process"):
        with pytest.raises(
            HunyuanProcessError,
            match=r"Shape process exited before becoming healthy \(returncode=17\)",
        ):
            process_manager.start_shape_server()

    assert "Shape process exited before becoming healthy" in caplog.text
    assert "returncode=17" in caplog.text
    assert process_manager.operational_state == "restart_failed"
