"""Design-pattern building blocks (Strategy, Observer, Factory, resilience)."""

from apps.common.patterns.circuit_breaker import CircuitBreaker, NoopCircuitBreaker, SimpleCircuitBreaker
from apps.common.patterns.factory import ServiceFactory
from apps.common.patterns.io_formats import get_export_strategy, get_import_strategy
from apps.common.patterns.observer import DomainEvent, DomainEventEmitter, domain_events
from apps.common.patterns.rate_limit import CacheRateLimitStore, MemoryRateLimitStore, RateLimitStore, RedisRateLimitStore
from apps.common.patterns.retry import ExponentialBackoffStrategy, FixedRetryStrategy, with_retry

__all__ = [
    "CircuitBreaker",
    "NoopCircuitBreaker",
    "SimpleCircuitBreaker",
    "ServiceFactory",
    "get_export_strategy",
    "get_import_strategy",
    "DomainEvent",
    "DomainEventEmitter",
    "domain_events",
    "CacheRateLimitStore",
    "MemoryRateLimitStore",
    "RedisRateLimitStore",
    "RateLimitStore",
    "ExponentialBackoffStrategy",
    "FixedRetryStrategy",
    "with_retry",
]
