from __future__ import annotations

import threading
from collections import defaultdict
from typing import DefaultDict, Tuple


class MetricsRegistry:
    def __init__(self, enabled: bool = True) -> None:
        self.enabled = enabled
        self._lock = threading.Lock()
        self.http_total: DefaultDict[Tuple[str, str, str], float] = defaultdict(float)
        self.http_duration: DefaultDict[Tuple[str, str], Tuple[float, int]] = (
            defaultdict(lambda: (0.0, 0))
        )
        self.jobs_total: DefaultDict[Tuple[str, str], float] = defaultdict(float)
        self.job_duration: DefaultDict[str, Tuple[float, int]] = defaultdict(
            lambda: (0.0, 0)
        )

    def observe_http(
        self, method: str, path: str, status: int, duration: float
    ) -> None:
        if not self.enabled:
            return
        with self._lock:
            self.http_total[(method, path, str(status))] += 1
            total, count = self.http_duration[(method, path)]
            self.http_duration[(method, path)] = (total + duration, count + 1)

    def observe_job(self, engine: str, status: str, duration: float = 0.0) -> None:
        if not self.enabled:
            return
        with self._lock:
            self.jobs_total[(engine, status)] += 1
            if status in {"completed", "failed"}:
                total, count = self.job_duration[engine]
                self.job_duration[engine] = (total + duration, count + 1)

    @staticmethod
    def _labels(**labels: str) -> str:
        return ",".join(f'{key}="{value}"' for key, value in labels.items())

    def render(self, container) -> str:
        lines = [
            "# TYPE forge3d_http_requests_total counter",
            "# TYPE forge3d_http_request_duration_seconds summary",
            "# TYPE forge3d_jobs_total counter",
            "# TYPE forge3d_job_duration_seconds summary",
            "# TYPE forge3d_queue_size gauge",
            "# TYPE forge3d_queue_capacity gauge",
            "# TYPE forge3d_queue_workers gauge",
            "# TYPE forge3d_engine_available gauge",
        ]
        with self._lock:
            for (method, path, status), value in sorted(self.http_total.items()):
                labels = self._labels(method=method, path=path, status=status)
                lines.append(f"forge3d_http_requests_total{{{labels}}} {value}")
            for (method, path), (total, count) in sorted(self.http_duration.items()):
                labels = self._labels(method=method, path=path)
                lines.append(
                    f"forge3d_http_request_duration_seconds_sum{{{labels}}} {total}"
                )
                lines.append(
                    f"forge3d_http_request_duration_seconds_count{{{labels}}} {count}"
                )
            for (engine, status), value in sorted(self.jobs_total.items()):
                labels = self._labels(engine=engine, status=status)
                lines.append(f"forge3d_jobs_total{{{labels}}} {value}")
            for engine, (total, count) in sorted(self.job_duration.items()):
                labels = self._labels(engine=engine)
                lines.append(f"forge3d_job_duration_seconds_sum{{{labels}}} {total}")
                lines.append(f"forge3d_job_duration_seconds_count{{{labels}}} {count}")
        queue = container.job_queue
        lines.append(f"forge3d_queue_size {queue.size}")
        lines.append(f"forge3d_queue_capacity {queue.max_size}")
        lines.append(f"forge3d_queue_workers {queue.workers_alive}")
        for engine in container.engines.list():
            value = 1 if engine.available() else 0
            lines.append(f'forge3d_engine_available{{engine="{engine.name}"}} {value}')
        return "\n".join(lines) + "\n"
