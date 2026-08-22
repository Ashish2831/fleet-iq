"""Design-pattern building blocks (Strategy, Observer, Factory, resilience)."""

from apps.common.patterns.adapter import FleetReadAdapter, GraphQLFleetAdapter, RestFleetAdapter
from apps.common.patterns.chain import PipelineHandler, run_chain
from apps.common.patterns.circuit_breaker import CircuitBreaker, NoopCircuitBreaker, SimpleCircuitBreaker
from apps.common.patterns.decorator import with_ttl_cache
from apps.common.patterns.factory import ServiceFactory
from apps.common.patterns.io_formats import get_export_strategy, get_import_strategy
from apps.common.patterns.observer import DomainEvent, DomainEventEmitter, domain_events
from apps.common.patterns.rate_limit import CacheRateLimitStore, MemoryRateLimitStore, RateLimitStore, RedisRateLimitStore
from apps.common.patterns.retry import ExponentialBackoffStrategy, FixedRetryStrategy, with_retry
from apps.common.patterns.session import CacheSessionStorage, MemorySessionStorage, SessionStorage, default_session_storage
from apps.common.patterns.validation import LenientValidationStrategy, StrictValidationStrategy, ValidationStrategy

__all__ = [
    "FleetReadAdapter",
    "GraphQLFleetAdapter",
    "RestFleetAdapter",
    "PipelineHandler",
    "run_chain",
    "CircuitBreaker",
    "NoopCircuitBreaker",
    "SimpleCircuitBreaker",
    "with_ttl_cache",
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
    "CacheSessionStorage",
    "MemorySessionStorage",
    "SessionStorage",
    "default_session_storage",
    "LenientValidationStrategy",
    "StrictValidationStrategy",
    "ValidationStrategy",
]
