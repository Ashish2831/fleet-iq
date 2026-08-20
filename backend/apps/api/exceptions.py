from rest_framework.views import exception_handler as drf_handler
from django.conf import settings

from apps.common.errors import ApiError
from apps.common.sanitize import sanitize_errors


def exception_handler(exc, context):
    if isinstance(exc, ApiError):
        request = context.get("request")
        return _problem(exc, getattr(request, "request_id", None))
    response = drf_handler(exc, context)
    if response is None:
        return None
    request = context.get("request")
    title = "Error"
    debug = bool(getattr(settings, "DEBUG", False))
    if isinstance(response.data, dict) and "detail" in response.data:
        detail = sanitize_errors(response.data["detail"], debug=debug)
    else:
        detail = sanitize_errors(response.data, debug=debug)
    # Never leak 500 internals in production responses
    if response.status_code >= 500 and not debug:
        detail = "An unexpected error occurred"
        title = "Internal Server Error"
    body = {
        "type": "about:blank",
        "title": title,
        "status": response.status_code,
        "detail": detail if isinstance(detail, str) else "Request failed",
        "errors": [] if (response.status_code >= 500 and not debug) else (
            sanitize_errors(response.data, debug=debug)
            if isinstance(response.data, (dict, list))
            else []
        ),
    }
    if request is not None:
        body["request_id"] = getattr(request, "request_id", None)
    response.data = body
    return response


def _problem(exc: ApiError, request_id=None):
    from rest_framework.response import Response

    return Response(
        {
            "type": "about:blank",
            "title": exc.title,
            "status": exc.status,
            "detail": exc.detail,
            "code": exc.code,
            "errors": [],
            "request_id": request_id,
        },
        status=exc.status,
    )
