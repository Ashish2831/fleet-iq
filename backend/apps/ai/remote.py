"""When CORE_API_URL is set, the AI process calls Core over HTTP instead of ORM."""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request

from django.conf import settings

from apps.api.jwt import access_token
from apps.common.errors import NotFound, Unavailable
from apps.common.patterns.circuit_breaker import CircuitOpenError, SimpleCircuitBreaker
from apps.common.patterns.retry import FixedRetryStrategy, with_retry

_core_breaker = SimpleCircuitBreaker(failure_threshold=5, reset_seconds=30.0)


def core_enabled() -> bool:
    return bool(getattr(settings, "CORE_API_URL", ""))


def _get(ctx, path: str, params: dict | None = None) -> dict | list:
    base = settings.CORE_API_URL.rstrip("/")
    url = f"{base}{path}"
    if params:
        url += "?" + urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
    token = access_token(ctx.user)
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}", "Accept": "application/json"})

    def call():
        try:
            with urllib.request.urlopen(req, timeout=8) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError:
            raise
        except urllib.error.URLError as exc:
            raise ConnectionError(str(exc.reason if hasattr(exc, "reason") else exc)) from exc

    try:
        return _core_breaker.call(
            lambda: with_retry(
                call,
                strategy=FixedRetryStrategy(attempts=2, delay=0.05),
                retry_on=(ConnectionError,),
                sleeper=lambda _: None,
            )
        )
    except CircuitOpenError as exc:
        raise Unavailable("Core circuit open") from exc
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise NotFound("Not found") from exc
        raise Unavailable(f"Core API {exc.code}") from exc
    except (urllib.error.URLError, ConnectionError) as exc:
        raise Unavailable(f"Core unreachable: {exc}") from exc


def fetch_shipment(ctx, *, id=None, number=None) -> dict | None:
    if not core_enabled():
        return None
    if id:
        return _get(ctx, f"/api/v1/shipments/{id}/")
    if number:
        data = _get(ctx, "/api/v1/search/shipments", {"q": number})
        hits = data.get("hits") or data.get("results") or []
        return hits[0] if hits else None
    return None
