from __future__ import annotations

import logging
import queue as queue_module
import threading
from typing import List, Optional, Union

from app.core.exceptions import JobQueueFullError
from app.domain.generation import GenerationResult
from app.domain.jobs import JobRepository, TextureStatus
from app.queue.contracts import JobQueue, QueuedJob
from app.queue.executor import JobExecutor
from app.texture.contracts import TextureRequest
from app.texture.executor import TextureExecutor, TextureQueuedJob

logger = logging.getLogger("forge3d.queue")
_STOP = object()
AUTO_TEXTURE_RESOLUTION = 512
AUTO_TEXTURE_QUALITY = "fast"


class LocalJobQueue(JobQueue):
    def __init__(
        self,
        executor: JobExecutor,
        jobs: JobRepository,
        concurrency: int = 1,
        max_size: int = 100,
        texture_executor: Optional[TextureExecutor] = None,
    ) -> None:
        if concurrency < 1:
            raise ValueError("Queue concurrency must be at least 1")
        if max_size < 1:
            raise ValueError("Queue max size must be at least 1")
        self.executor = executor
        self.jobs = jobs
        self.concurrency = concurrency
        self.max_size = max_size
        self.texture_executor = texture_executor
        self._queue: queue_module.Queue[Union[QueuedJob, object]] = queue_module.Queue(
            maxsize=max_size
        )
        self._workers: List[threading.Thread] = []
        self._enqueue_lock = threading.Lock()
        self._started = False
        self.executor.on_completed = self._enqueue_automatic_texture

    def _enqueue_automatic_texture(
        self, task: QueuedJob, result: GenerationResult
    ) -> None:
        if task.job.engine != "hunyuan" or self.texture_executor is None:
            return
        completed = self.jobs.get(task.job.id)
        if completed is None or completed.texture_status is not None:
            return
        texture_task = TextureQueuedJob(
            completed,
            task.context,
            result.artifact_path,
            task.image_path,
            TextureRequest(AUTO_TEXTURE_RESOLUTION, AUTO_TEXTURE_QUALITY),
        )
        try:
            running_in_worker = threading.current_thread() in self._workers
            if running_in_worker:
                self.texture_executor.execute(texture_task)
            else:
                self.enqueue_texture(texture_task)
            logger.info(
                "automatic_texture_scheduled job_id=%s engine=hunyuan mode=%s resolution=%s quality=%s",
                completed.id,
                "inline_worker" if running_in_worker else "queued",
                AUTO_TEXTURE_RESOLUTION,
                AUTO_TEXTURE_QUALITY,
                extra={
                    "job_id": str(completed.id),
                    "engine": "hunyuan",
                    "resolution": AUTO_TEXTURE_RESOLUTION,
                    "quality": AUTO_TEXTURE_QUALITY,
                    "mode": "inline_worker" if running_in_worker else "queued",
                },
            )
        except Exception as error:
            current = self.jobs.get(completed.id) or completed
            if current.texture_status is None:
                self.jobs.save(
                    current.transition_texture(
                        TextureStatus.FAILED,
                        error="Não foi possível iniciar a texturização",
                        metadata={
                            "status": "error",
                            "step": "enqueue",
                            "error_code": type(error).__name__,
                        },
                    )
                )
            raise

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

    def enqueue_texture(self, task: TextureQueuedJob) -> None:
        with self._enqueue_lock:
            if self._queue.full():
                raise JobQueueFullError("A fila local está cheia")
            self.jobs.save(task.job)
            self._queue.put_nowait(task)

    def _worker(self) -> None:
        while True:
            task = self._queue.get()
            try:
                if task is _STOP:
                    return
                assert isinstance(task, (QueuedJob, TextureQueuedJob))
                try:
                    if isinstance(task, TextureQueuedJob):
                        if self.texture_executor is None:
                            raise RuntimeError("Texture executor unavailable")
                        self.texture_executor.execute(task)
                    else:
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
