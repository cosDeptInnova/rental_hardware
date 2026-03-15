import time
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from shared.utils.request_id import new_request_id


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        rid = request.headers.get("X-Request-Id", new_request_id())
        request.state.request_id = rid
        request.state.started = time.time()
        response = await call_next(request)
        response.headers["X-Request-Id"] = rid
        return response
