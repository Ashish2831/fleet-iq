"""Chain of Responsibility — sequential request handlers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class PipelineRequest:
    path: str
    method: str
    headers: dict[str, str] = field(default_factory=dict)
    user: Any = None
    extra: dict[str, Any] = field(default_factory=dict)


class PipelineHandler(ABC):
    @abstractmethod
    def handle(self, request: PipelineRequest, nxt: Callable[[], Any]) -> Any: ...


class AuthRequiredHandler(PipelineHandler):
    def handle(self, request: PipelineRequest, nxt: Callable[[], Any]) -> Any:
        auth = request.headers.get("authorization") or request.headers.get("Authorization") or ""
        if request.user is None and not auth.startswith("Bearer "):
            raise PermissionError("Authentication required")
        return nxt()


class RequestIdHandler(PipelineHandler):
    def handle(self, request: PipelineRequest, nxt: Callable[[], Any]) -> Any:
        if not request.headers.get("x-request-id") and not request.headers.get("X-Request-ID"):
            request.extra.setdefault("request_id", "generated")
        return nxt()


class TenantBoundHandler(PipelineHandler):
    def handle(self, request: PipelineRequest, nxt: Callable[[], Any]) -> Any:
        user = request.user
        if user is not None and getattr(user, "tenant_id", None) is None:
            raise PermissionError("Tenant required")
        return nxt()


def run_chain(handlers: list[PipelineHandler], request: PipelineRequest, terminal: Callable[[], Any]) -> Any:
    index = 0

    def nxt():
        nonlocal index
        if index >= len(handlers):
            return terminal()
        handler = handlers[index]
        index += 1
        return handler.handle(request, nxt)

    return nxt()
