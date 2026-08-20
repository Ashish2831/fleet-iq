"""Batch read API — collapse multiple GET /api/v1/* calls into one round trip."""

from __future__ import annotations

from urllib.parse import urlsplit

from django.urls import Resolver404, resolve
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.api.permissions import IsTenantAuthenticated
from apps.common.errors import BadRequest

MAX_BATCH = 20
ALLOWED_PREFIX = "/api/v1/"
BLOCKED_SUFFIXES = ("/batch", "/auth/login", "/auth/refresh")


def _normalize_path(raw: str) -> str:
    path = (raw or "").strip()
    parts = urlsplit(path)
    if parts.scheme or parts.netloc:
        raise BadRequest("path must be relative")
    if not path.startswith("/"):
        path = "/" + path
    parts = urlsplit(path)
    if parts.scheme or parts.netloc:
        raise BadRequest("path must be relative")
    full = parts.path
    if parts.query:
        full = f"{full}?{parts.query}"
    return full


def _allowed(path: str) -> bool:
    path_only = path.split("?", 1)[0].rstrip("/") or "/"
    if not path_only.startswith(ALLOWED_PREFIX.rstrip("/")):
        return False
    if path_only == "/api/v1/batch":
        return False
    for blocked in BLOCKED_SUFFIXES:
        if path_only.endswith(blocked) or path_only.endswith(blocked.rstrip("/")):
            return False
    return True


def _dispatch(parent, method: str, path: str):
    path_only, _, query = path.partition("?")
    try:
        match = resolve(path_only)
    except Resolver404:
        return 404, {"detail": "Not found"}

    factory = APIRequestFactory()
    headers = {}
    auth = parent.META.get("HTTP_AUTHORIZATION")
    if auth:
        headers["HTTP_AUTHORIZATION"] = auth
    rid = getattr(parent, "request_id", None)
    if rid:
        headers["HTTP_X_REQUEST_ID"] = rid

    django_req = factory.generic(method, path if query else path_only, **headers)
    force_authenticate(django_req, user=parent.user, token=getattr(parent, "auth", None))
    django_req.user = parent.user
    if hasattr(parent, "tenant"):
        django_req.tenant = parent.tenant

    response = match.func(django_req, *match.args, **match.kwargs)
    if hasattr(response, "render") and callable(response.render) and not getattr(response, "is_rendered", True):
        response.render()

    status = getattr(response, "status_code", 500)
    if hasattr(response, "data"):
        body = response.data
    else:
        try:
            body = response.content.decode("utf-8")
        except Exception:
            body = None
    return status, body


@api_view(["POST"])
@permission_classes([IsTenantAuthenticated])
def batch(request):
    items = request.data.get("requests")
    if not isinstance(items, list):
        raise BadRequest("requests must be a list")
    if len(items) > MAX_BATCH:
        raise BadRequest(f"max {MAX_BATCH} requests per batch")

    responses = []
    for item in items:
        if not isinstance(item, dict):
            responses.append({"id": None, "success": False, "status": 400, "error": "invalid item"})
            continue
        req_id = item.get("id")
        method = str(item.get("method") or "GET").upper()
        if method != "GET":
            responses.append(
                {"id": req_id, "success": False, "status": 405, "error": "only GET is allowed in batch"}
            )
            continue
        try:
            path = _normalize_path(str(item.get("path") or ""))
        except BadRequest as exc:
            responses.append({"id": req_id, "success": False, "status": 400, "error": exc.detail})
            continue
        if not _allowed(path):
            responses.append({"id": req_id, "success": False, "status": 400, "error": "path not allowed"})
            continue
        status, body = _dispatch(request, method, path)
        ok = 200 <= status < 400
        entry = {"id": req_id, "success": ok, "status": status}
        if ok:
            entry["data"] = body
        else:
            entry["error"] = body if isinstance(body, (str, dict, list)) else "request failed"
        responses.append(entry)

    return Response({"success": True, "responses": responses})
