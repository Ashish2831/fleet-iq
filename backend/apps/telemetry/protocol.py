from __future__ import annotations

from datetime import datetime
from typing import Protocol


class TelemetryStore(Protocol):
    """GPS history. Redis is still the live pin; this is never the live map."""

    def claim_event(self, event_id: str) -> bool:
        """True if this event_id is new (insert into the dedupe collection)."""

    def insert_raw(self, docs: list[dict]) -> int:
        ...

    def track(
        self,
        *,
        tenant_id: str,
        vehicle_id: str,
        start: datetime,
        end: datetime,
        source: str = "raw",
    ) -> list[dict]:
        ...

    def insert_minute(self, docs: list[dict]) -> int:
        ...

    def expire_raw(self, older_than: datetime) -> int:
        ...

    def flush(self) -> None:
        ...

    def raw_count(self, *, tenant_id: str | None = None) -> int:
        ...
