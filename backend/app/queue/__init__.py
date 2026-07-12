"""Local background queue and future queue adapter contracts."""

from app.queue.contracts import JobQueue, QueuedJob
from app.queue.local import LocalJobQueue

__all__ = ["JobQueue", "LocalJobQueue", "QueuedJob"]
