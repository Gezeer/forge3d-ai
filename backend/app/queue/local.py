from __future__ import annotations

import logging
import queue as queue_module
import threading
from typing import List, Union

from app.core.exceptions import JobQueueFullError
from app.domain.jobs import JobRepository
from app.queue.contracts import JobQueue, QueuedJob
from app.queue.executor import JobExecutor

logger = logging.getLogger("forge3d.queue")
_STOP = object()


class LocalJobQueue(JobQueue):
    def __init__(
        self,
        executor: JobExecutor,
        jobs: JobRepository,
        concurrency: int = 1,
        max_size: int = 100,
    ) -> None:
        if concurrency < 1:
            raise ValueError("Queue concurrency must be at least 1")
        if max_size < 1:
            raise ValueError("Queue max size must be at least 1")
        self.executor = executor
        self.jobs = jobs
        self.concurrency = concurrency
        self.max_size = max_size
        self._queue: queue_module.Queue[Union[QueuedJob, object]] = queue_module.Queue(
            maxsize=max_size
        )
        self._workers: List[threading.Thread] = []
        self._enqueue_lock = threading.Lock()
        self._started = False

    @property
    def started(self) -> bool:
        return self._started

    @property
    def workers_alive(self) -> int:
        return sum(worker.is_alive() for worker in self._workers)

    @property
    def size(self) -> int:
        return self._queue.qsize()

    def start(self) -> None:
        if self._started:
            return
        self._started = True
        self._workers = [
            threading.Thread(
                target=self._worker,
                name=f"forge3d-worker-{index + 1}",
                daemon=False,
            )
            for index in range(self.concurrency)
        ]
        for worker in self._workers:
            worker.start()
        logger.info(
            "local_queue_started",
            extra={"concurrency": self.concurrency, "max_size": self.max_size},
        )

    def enqueue(self, task: QueuedJob) -> None:
        with self._enqueue_lock:
            if self._queue.full():
                raise JobQueueFullError("A fila local está cheia")
            self.jobs.save(task.job)
            if self.executor.metrics:
                self.executor.metrics.observe_job(task.job.engine, "queued")
            try:
                self._queue.put_nowait(task)
            except queue_module.Full as exc:
                raise JobQueueFullError("A fila local está cheia") from exc
        logger.info(
            "job_enqueued job_id=%s engine=%s status=%s",
            str(task.job.id),
            task.job.engine,
            task.job.status.value,
            extra={
                "job_id": str(task.job.id),
                "engine": task.job.engine,
                "job_status": task.job.status.value,
            },
        )

    def _worker(self) -> None:
        while True:
            task = self._queue.get()
            try:
                if task is _STOP:
                    return
                assert isinstance(task, QueuedJob)
                try:
                    self.executor.execute(task)
                except Exception as error:
                    logger.error(
                        "job_execution_failed job_id=%s engine=%s error_code=%s",
                        str(task.job.id),
                        task.job.engine,
                        type(error).__name__,
                        extra={
                            "job_id": str(task.job.id),
                            "engine": task.job.engine,
                            "error_code": type(error).__name__,
                        },
                    )
            finally:
                self._queue.task_done()

    def stop(self) -> None:
        if not self._started:
            return
        self._queue.join()
        for _ in self._workers:
            self._queue.put(_STOP)
        for worker in self._workers:
            worker.join()
        self._workers = []
        self._started = False
        logger.info("local_queue_stopped")
