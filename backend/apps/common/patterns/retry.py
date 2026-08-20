"""Retry strategies — swap backoff without changing callers."""

from __future__ import annotations

import random
import time
from abc import ABC, abstractmethod
from typing import Callable, TypeVar

T = TypeVar("T")


class RetryStrategy(ABC):
    @abstractmethod
    def delays(self) -> list[float]:
        """Sleep seconds before each retry (not including the first attempt)."""


class FixedRetryStrategy(RetryStrategy):
    def __init__(self, attempts: int = 3, delay: float = 0.05):
        self.attempts = max(0, attempts)
        self.delay = delay

    def delays(self) -> list[float]:
        return [self.delay] * self.attempts


class ExponentialBackoffStrategy(RetryStrategy):
    def __init__(
        self,
        attempts: int = 3,
        base: float = 0.05,
        factor: float = 2.0,
        jitter: float = 0.1,
        max_delay: float = 2.0,
    ):
        self.attempts = max(0, attempts)
        self.base = base
        self.factor = factor
        self.jitter = jitter
        self.max_delay = max_delay

    def delays(self) -> list[float]:
        out = []
        delay = self.base
        for _ in range(self.attempts):
            jittered = delay * (1 + random.uniform(-self.jitter, self.jitter))
            out.append(min(self.max_delay, max(0.0, jittered)))
            delay *= self.factor
        return out


def with_retry(
    fn: Callable[[], T],
    *,
    strategy: RetryStrategy | None = None,
    retry_on: tuple[type[BaseException], ...] = (Exception,),
    sleeper: Callable[[float], None] = time.sleep,
) -> T:
    strategy = strategy or ExponentialBackoffStrategy()
    delays = strategy.delays()
    attempt = 0
    while True:
        try:
            return fn()
        except retry_on:
            if attempt >= len(delays):
                raise
            sleeper(delays[attempt])
            attempt += 1
