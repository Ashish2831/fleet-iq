class ApiError(Exception):
    def __init__(self, title: str, *, status: int = 400, code: str = "BAD_REQUEST", detail: str = ""):
        self.title = title
        self.status = status
        self.code = code
        self.detail = detail or title
        super().__init__(self.detail)


class NotFound(ApiError):
    def __init__(self, detail="Not found"):
        super().__init__("Not Found", status=404, code="NOT_FOUND", detail=detail)


class Forbidden(ApiError):
    def __init__(self, detail="Forbidden"):
        super().__init__("Forbidden", status=403, code="FORBIDDEN", detail=detail)


class Conflict(ApiError):
    def __init__(self, detail="Conflict"):
        super().__init__("Conflict", status=409, code="CONFLICT", detail=detail)


class Unauthorized(ApiError):
    def __init__(self, detail="Authentication required"):
        super().__init__("Unauthorized", status=401, code="UNAUTHORIZED", detail=detail)


class Unavailable(ApiError):
    def __init__(self, detail="Service unavailable"):
        super().__init__("Unavailable", status=503, code="UNAVAILABLE", detail=detail)
