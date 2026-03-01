from __future__ import annotations

import time
from dataclasses import dataclass, field
from threading import Lock


@dataclass
class RouteMetrics:
    requests_total: int = 0
    error_requests_total: int = 0
    total_duration_ms: float = 0.0
    max_duration_ms: float = 0.0
    status_codes: dict[str, int] = field(default_factory=dict)

    def snapshot(self) -> dict[str, object]:
        avg_duration_ms = (
            round(self.total_duration_ms / self.requests_total, 3) if self.requests_total else 0.0
        )
        return {
            "requests_total": self.requests_total,
            "error_requests_total": self.error_requests_total,
            "avg_duration_ms": avg_duration_ms,
            "max_duration_ms": round(self.max_duration_ms, 3),
            "status_codes": dict(sorted(self.status_codes.items())),
        }


class HTTPMetricsTracker:
    def __init__(self) -> None:
        self._lock = Lock()
        self._reset_unlocked()

    def _reset_unlocked(self) -> None:
        self._started_at = time.time()
        self._requests_total = 0
        self._requests_in_flight = 0
        self._error_requests_total = 0
        self._total_duration_ms = 0.0
        self._max_duration_ms = 0.0
        self._status_codes: dict[str, int] = {}
        self._routes: dict[str, RouteMetrics] = {}

    def reset(self) -> None:
        with self._lock:
            self._reset_unlocked()

    def request_started(self) -> None:
        with self._lock:
            self._requests_in_flight += 1

    def request_finished(
        self,
        *,
        method: str,
        route_label: str,
        status_code: int,
        duration_ms: float,
    ) -> None:
        route_key = f"{method.upper()} {route_label}"
        status_key = str(status_code)

        with self._lock:
            self._requests_total += 1
            self._requests_in_flight = max(0, self._requests_in_flight - 1)
            self._total_duration_ms += duration_ms
            self._max_duration_ms = max(self._max_duration_ms, duration_ms)
            self._status_codes[status_key] = self._status_codes.get(status_key, 0) + 1

            route_metrics = self._routes.setdefault(route_key, RouteMetrics())
            route_metrics.requests_total += 1
            route_metrics.total_duration_ms += duration_ms
            route_metrics.max_duration_ms = max(route_metrics.max_duration_ms, duration_ms)
            route_metrics.status_codes[status_key] = (
                route_metrics.status_codes.get(status_key, 0) + 1
            )

            if status_code >= 400:
                self._error_requests_total += 1
                route_metrics.error_requests_total += 1

    def snapshot(self) -> dict[str, object]:
        with self._lock:
            avg_duration_ms = (
                round(self._total_duration_ms / self._requests_total, 3)
                if self._requests_total
                else 0.0
            )
            routes = {
                route_key: route_metrics.snapshot()
                for route_key, route_metrics in sorted(self._routes.items())
            }
            return {
                "uptime_seconds": round(time.time() - self._started_at, 3),
                "started_at_unix": round(self._started_at, 3),
                "http": {
                    "requests_total": self._requests_total,
                    "requests_in_flight": self._requests_in_flight,
                    "error_requests_total": self._error_requests_total,
                    "avg_duration_ms": avg_duration_ms,
                    "max_duration_ms": round(self._max_duration_ms, 3),
                    "status_codes": dict(sorted(self._status_codes.items())),
                    "routes": routes,
                },
            }


http_metrics = HTTPMetricsTracker()


def get_metrics_snapshot() -> dict[str, object]:
    return http_metrics.snapshot()


def reset_metrics() -> None:
    http_metrics.reset()
