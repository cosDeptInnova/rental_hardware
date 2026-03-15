import time
from collections import defaultdict, deque
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, limit_per_minute: int = 120):
        super().__init__(app)
        self.limit = limit_per_minute
        self.hits = defaultdict(deque)

    async def dispatch(self, request: Request, call_next):
        key = request.headers.get("X-API-Key", "anonymous")
        now = time.time()
        queue = self.hits[key]
        while queue and queue[0] < now - 60:
            queue.popleft()
        if len(queue) >= self.limit:
            return JSONResponse(status_code=429, content={"detail": "Rate limit exceeded"})
        queue.append(now)
        return await call_next(request)
