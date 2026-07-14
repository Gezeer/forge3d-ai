from __future__ import annotations

import threading

import pytest
from app.gpu.lock import GPULock, GPULockTimeoutError


def test_gpu_lock_blocks_concurrent_users(tmp_path):
    path = tmp_path / "gpu.lock"
    first = GPULock(path, timeout=1)
    first.acquire()
    errors = []

    def contender():
        try:
            GPULock(path, timeout=0.05).acquire()
        except Exception as error:
            errors.append(error)

    thread = threading.Thread(target=contender)
    thread.start()
    thread.join()
    first.release()

    assert len(errors) == 1
    assert isinstance(errors[0], GPULockTimeoutError)


def test_gpu_lock_is_released_after_exception(tmp_path):
    path = tmp_path / "gpu.lock"

    with pytest.raises(RuntimeError):
        with GPULock(path, timeout=1):
            raise RuntimeError("failure")

    with GPULock(path, timeout=1):
        assert path.is_file()
