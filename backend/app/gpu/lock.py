from __future__ import annotations

import fcntl
import logging
import threading
import time
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger("forge3d.gpu")
_THREAD_LOCKS: Dict[str, threading.Lock] = {}
_THREAD_LOCKS_GUARD = threading.Lock()


class GPULockTimeoutError(TimeoutError):
    pass


class GPULock:
    def __init__(
        self,
        path: Path = Path("/tmp/forge3d-gpu.lock"),
        timeout: float = 1800.0,
        poll_interval: float = 0.1,
    ) -> None:
        self.path = path.expanduser().resolve()
        self.timeout = timeout
        self.poll_interval = poll_interval
        self._stream = None
        self._thread_lock: Optional[threading.Lock] = None

    def acquire(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        key = str(self.path)
        with _THREAD_LOCKS_GUARD:
            thread_lock = _THREAD_LOCKS.setdefault(key, threading.Lock())
        if not thread_lock.acquire(timeout=self.timeout):
            raise GPULockTimeoutError("Timeout aguardando acesso exclusivo à GPU")
        self._thread_lock = thread_lock
        stream = self.path.open("a+")
        deadline = time.monotonic() + self.timeout
        try:
            while True:
                try:
                    fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    self._stream = stream
                    logger.info("gpu_lock_acquired path=%s", self.path)
                    return
                except BlockingIOError:
                    if time.monotonic() >= deadline:
                        raise GPULockTimeoutError(
                            "Timeout aguardando acesso exclusivo à GPU"
                        )
                    time.sleep(self.poll_interval)
        except Exception:
            stream.close()
            thread_lock.release()
            self._thread_lock = None
            raise

    def release(self) -> None:
        if self._stream is not None:
            fcntl.flock(self._stream.fileno(), fcntl.LOCK_UN)
            self._stream.close()
            self._stream = None
        if self._thread_lock is not None:
            self._thread_lock.release()
            self._thread_lock = None
        logger.info("gpu_lock_released path=%s", self.path)

    def __enter__(self) -> "GPULock":
        self.acquire()
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.release()
