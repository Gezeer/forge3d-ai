from __future__ import annotations

import errno
import importlib.util
import shutil
import sys
import tempfile
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/run_hunyuan_paint.py"
SPEC = importlib.util.spec_from_file_location("run_hunyuan_paint_cache_test", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def configured(tmp_path: Path, **extra):
    environment = {
        "FORGE3D_TEXTURE_CACHE": str(tmp_path / "texture-cache"),
        "FORGE3D_TEXTURE_MIN_FREE_BYTES": "0",
        "FORGE3D_TEXTURE_DOWNLOAD_ATTEMPTS": "3",
        "FORGE3D_TEXTURE_DOWNLOAD_RETRY_SECONDS": "0",
        **extra,
    }
    layout = MODULE.configure_cache_environment(environ=environment)
    return layout, environment


def test_custom_cache_configures_all_model_directories(tmp_path: Path):
    layout, environment = configured(tmp_path)

    assert layout.root == (tmp_path / "texture-cache").resolve()
    assert environment["HF_HOME"] == str(layout.cache)
    assert environment["HUGGINGFACE_HUB_CACHE"] == str(layout.hub)
    assert environment["HF_HUB_CACHE"] == str(layout.hub)
    assert environment["TRANSFORMERS_CACHE"] == str(layout.transformers)
    assert environment["HF_DATASETS_CACHE"] == str(layout.datasets)
    assert environment["XDG_CACHE_HOME"] == str(layout.cache)
    assert environment["TORCH_HOME"] == str(layout.torch)
    assert environment["DIFFUSERS_CACHE"] == str(layout.hub)
    assert environment["HF_HUB_DISABLE_XET"] == "1"
    assert all(
        directory.is_dir()
        for directory in (
            layout.cache,
            layout.hub,
            layout.transformers,
            layout.datasets,
            layout.torch,
        )
    )


def test_nonexistent_cache_is_created(tmp_path: Path):
    root = tmp_path / "new-cache"
    assert not root.exists()

    layout = MODULE.configure_cache_environment(root, environ={})

    assert layout.root.is_dir()
    assert layout.hub.is_dir()


def test_existing_cache_is_preserved_and_skips_download_space_check(tmp_path: Path):
    layout, _ = configured(tmp_path)
    cached = layout.hub / "models--tencent--Hunyuan3D-2.1" / "blob"
    cached.parent.mkdir(parents=True)
    cached.write_bytes(b"cached-model")
    layout.ready_marker.touch()

    MODULE.ensure_cache_capacity(
        layout,
        10**15,
        disk_usage=lambda _: pytest.fail("disk space should not be checked"),
    )

    assert cached.read_bytes() == b"cached-model"


def test_interrupted_download_retries_with_exponential_backoff(tmp_path: Path):
    layout, environment = configured(
        tmp_path, FORGE3D_TEXTURE_DOWNLOAD_RETRY_SECONDS="0.25"
    )
    attempts = []
    delays = []
    pipeline = object()

    def builder(root, resolution):
        attempts.append((root, resolution))
        if len(attempts) < 3:
            raise ConnectionError("download interrupted")
        return pipeline

    result = MODULE.load_pipeline_with_retry(
        tmp_path,
        512,
        layout,
        builder=builder,
        sleeper=delays.append,
        environ=environment,
    )

    assert result is pipeline
    assert len(attempts) == 3
    assert delays == [0.25, 0.5]
    assert layout.ready_marker.is_file()


def test_retry_reuses_partial_huggingface_download(tmp_path: Path):
    layout, environment = configured(tmp_path)
    partial = layout.hub / "models--paint" / "blobs" / "weights.incomplete"
    partial.parent.mkdir(parents=True)
    partial.write_bytes(b"partial")
    observed = []

    def builder(root, resolution):
        observed.append((partial.read_bytes(), environment["HF_HUB_CACHE"]))
        if len(observed) == 1:
            raise TimeoutError("network timeout")
        return object()

    MODULE.load_pipeline_with_retry(
        tmp_path,
        512,
        layout,
        builder=builder,
        sleeper=lambda _: None,
        environ=environment,
    )

    assert observed == [
        (b"partial", str(layout.hub)),
        (b"partial", str(layout.hub)),
    ]


def test_custom_tmpdir_is_used_without_system_cache(tmp_path: Path):
    custom_tmp = tmp_path / "paint-tmp"
    layout, environment = configured(tmp_path, TMPDIR=str(custom_tmp))

    assert layout.tmp == custom_tmp.resolve()
    assert environment["TMPDIR"] == str(custom_tmp.resolve())
    assert environment["TMP"] == str(custom_tmp.resolve())
    assert environment["TEMP"] == str(custom_tmp.resolve())
    assert custom_tmp.is_dir()
    assert "/root/.cache" not in " ".join(environment.values())


def test_python_tempfile_uses_custom_tmpdir(tmp_path: Path, monkeypatch):
    custom_tmp = tmp_path / "python-temp"
    cache = tmp_path / "cache"
    monkeypatch.setenv("FORGE3D_TEXTURE_CACHE", str(cache))
    monkeypatch.setenv("TMPDIR", str(custom_tmp))
    previous = tempfile.tempdir
    try:
        MODULE.configure_cache_environment()
        assert tempfile.gettempdir() == str(custom_tmp.resolve())
    finally:
        tempfile.tempdir = previous


def test_exhausted_download_returns_safe_resumable_error(tmp_path: Path):
    layout, environment = configured(tmp_path, FORGE3D_TEXTURE_DOWNLOAD_ATTEMPTS="2")

    with pytest.raises(MODULE.TextureCacheError, match="preservados para retomada"):
        MODULE.load_pipeline_with_retry(
            tmp_path,
            512,
            layout,
            builder=lambda *_: (_ for _ in ()).throw(ConnectionError("secret url")),
            sleeper=lambda _: None,
            environ=environment,
        )


def test_insufficient_space_returns_friendly_error(tmp_path: Path):
    layout, _ = configured(tmp_path)
    usage = shutil._ntuple_diskusage(total=100, used=90, free=10)

    with pytest.raises(MODULE.TextureCacheError, match="Espaço insuficiente"):
        MODULE.ensure_cache_capacity(layout, 11, disk_usage=lambda _: usage)


def test_disk_quota_error_stops_before_another_native_attempt(tmp_path: Path):
    layout, environment = configured(tmp_path)
    calls = []

    def quota_failure(*_):
        calls.append(1)
        raise OSError(errno.EDQUOT, "Disk quota exceeded")

    with pytest.raises(MODULE.TextureCacheError, match="Quota excedida"):
        MODULE.load_pipeline_with_retry(
            tmp_path,
            512,
            layout,
            builder=quota_failure,
            sleeper=lambda _: None,
            environ=environment,
        )

    assert calls == [1]
