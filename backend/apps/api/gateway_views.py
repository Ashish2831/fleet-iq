import json

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

from asgiref.sync import async_to_sync

from apps.api.federation import execute_federated
from config.schema import get_context


@csrf_exempt
def graphql_gateway(request):
    if request.method == "GET":
        return JsonResponse({"status": "ok", "gateway": True, "phase": "I"})
    try:
        body = json.loads(request.body or b"{}")
    except json.JSONDecodeError:
        return JsonResponse({"errors": [{"message": "invalid JSON"}]}, status=400)
    query = body.get("query") or ""
    variables = body.get("variables") or {}
    context = async_to_sync(get_context)(request, None)
    result = execute_federated(query, variables, context)
    return JsonResponse(result)
