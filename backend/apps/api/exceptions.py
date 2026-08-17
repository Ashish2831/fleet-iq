from rest_framework.views import exception_handler as drf_handler

from apps.common.errors import ApiError


def exception_handler(exc, context):
    if isinstance(exc, ApiError):
        request = context.get("request")
        return _problem(exc, getattr(request, "request_id", None))
    response = drf_handler(exc, context)
    if response is None:
        return None
    request = context.get("request")
    title = "Error"
    if isinstance(response.data, dict) and "detail" in response.data:
        detail = str(response.data["detail"])
    else:
        detail = str(response.data)
    body = {
        "type": "about:blank",
        "title": title,
        "status": response.status_code,
        "detail": detail,
        "errors": response.data if isinstance(response.data, (dict, list)) else [],
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
