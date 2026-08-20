"""Circuit breaker strategies — fail fast when a dependency is unhealthy."""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from threading import Lock


class CircuitOpenError(RuntimeError):
    pass


class CircuitBreaker(ABC):
    @abstractmethod
    def allow(self) -> bool:
        ...

    @abstractmethod
    def record_success(self) -> None:
        ...

    @abstractmethod
    def record_failure(self) -> None:
        ...

    def call(self, fn):
        if not self.allow():
            raise CircuitOpenError("circuit open")
        try:
            result = fn()
        except Exception:
            self.record_failure()
            raise
        self.record_success()
        return result


class NoopCircuitBreaker(CircuitBreaker):
    def allow(self) -> bool:
        return True

    def record_success(self) -> None:
        return None

    def record_failure(self) -> None:
        return None


class SimpleCircuitBreaker(CircuitBreaker):
    def __init__(self, *, failure_threshold: int = 5, reset_seconds: float = 30.0):
        self.failure_threshold = failure_threshold
        self.reset_seconds = reset_seconds
        self._failures = 0
        self._opened_at: float | None = None
        self._lock = Lock()

    def allow(self) -> bool:
        with self._lock:
            if self._opened_at is None:
                return True
            if time.monotonic() - self._opened_at >= self.reset_seconds:
                self._opened_at = None
                self._failures = 0
                return True
            return False

    def record_success(self) -> None:
        with self._lock:
            self._failures = 0
            self._opened_at = None

    def record_failure(self) -> None:
        with self._lock:
            self._failures += 1
            if self._failures >= self.failure_threshold:
                self._opened_at = time.monotonic()
