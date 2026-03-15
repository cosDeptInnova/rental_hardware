from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from shared.utils.request_id import new_request_id


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request.state.request_id = request.headers.get("X-Request-Id", new_request_id())
        response = await call_next(request)
        response.headers["X-Request-Id"] = request.state.request_id
        return response
