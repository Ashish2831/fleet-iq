import base64

from django.conf import settings
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response


@api_view(["GET"])
@permission_classes([AllowAny])
def jwks(_request):
    """HS256 'JWKS' for local services. Production would publish RS256 from Core."""
    raw = settings.JWT_SECRET.encode("utf-8")
    k = base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")
    return Response(
        {
            "keys": [
                {
                    "kty": "oct",
                    "kid": getattr(settings, "JWT_KID", "fleetiq-hs256"),
                    "alg": "HS256",
                    "use": "sig",
                    "k": k,
                }
            ]
        }
    )
