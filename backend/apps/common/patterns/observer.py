"""Observer — in-process domain events (complements Kafka outbox)."""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Callable

logger = logging.getLogger(__name__)

Handler = Callable[["DomainEvent"], None]


@dataclass(frozen=True)
class DomainEvent:
    type: str
    payload: dict[str, Any] = field(default_factory=dict)
    tenant_id: str | None = None
    aggregate_id: str | None = None


class DomainEventEmitter:
    """Open for extension: register handlers without changing publishers."""

    def __init__(self):
        self._handlers: dict[str, list[Handler]] = defaultdict(list)

    def on(self, event_type: str, handler: Handler) -> None:
        self._handlers[event_type].append(handler)

    def off(self, event_type: str, handler: Handler | None = None) -> None:
        if handler is None:
            self._handlers.pop(event_type, None)
            return
        self._handlers[event_type] = [h for h in self._handlers.get(event_type, []) if h is not handler]

    def emit(self, event: DomainEvent | str, payload: dict | None = None, **meta) -> None:
        if isinstance(event, str):
            event = DomainEvent(type=event, payload=payload or {}, **meta)
        for handler in list(self._handlers.get(event.type, [])) + list(self._handlers.get("*", [])):
            try:
                handler(event)
            except Exception:
                logger.exception("domain event handler failed type=%s", event.type)

    def clear(self) -> None:
        self._handlers.clear()


domain_events = DomainEventEmitter()
