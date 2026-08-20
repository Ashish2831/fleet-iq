import logging
import uuid

from django.utils.deprecation import MiddlewareMixin

logger = logging.getLogger("apps.api.request")


class RequestIdMiddleware(MiddlewareMixin):
    def process_request(self, request):
        request.request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        from apps.events.context import set_correlation_id

        set_correlation_id(request.request_id)

    def process_response(self, request, response):
        rid = getattr(request, "request_id", "")
        response["X-Request-ID"] = rid
        if request.path.startswith("/api/") or request.path.startswith("/graphql"):
            logger.info(
                "request completed",
                extra={
                    "request_id": rid,
                    "correlation_id": rid,
                    "method": request.method,
                    "path": request.path,
                    "status": getattr(response, "status_code", None),
                },
            )
        return response
