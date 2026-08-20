from rest_framework.pagination import LimitOffsetPagination
from rest_framework.response import Response


class StandardLimitOffsetPagination(LimitOffsetPagination):
    """Consistent list envelope: count / next / previous / results / limit / offset."""

    default_limit = 25
    max_limit = 100

    def get_paginated_response(self, data):
        return Response(
            {
                "count": self.count,
                "next": self.get_next_link(),
                "previous": self.get_previous_link(),
                "limit": self.limit,
                "offset": self.offset,
                "results": data,
            }
        )

    def get_paginated_response_schema(self, schema):
        return {
            "type": "object",
            "properties": {
                "count": {"type": "integer"},
                "next": {"type": "string", "nullable": True, "format": "uri"},
                "previous": {"type": "string", "nullable": True, "format": "uri"},
                "limit": {"type": "integer"},
                "offset": {"type": "integer"},
                "results": schema,
            },
        }
