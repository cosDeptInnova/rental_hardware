import time
from datetime import datetime
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from apps.bastion_control_plane.db.session import SessionLocal
from apps.bastion_control_plane.models.db_models import RequestLog


class AuditMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        started = time.time()
        response = await call_next(request)
        duration_ms = (time.time() - started) * 1000
        body = getattr(request.state, "raw_body", b"")
        db = SessionLocal()
        try:
            log = RequestLog(
                request_id=getattr(request.state, "request_id", ""),
                tenant_id=getattr(request.state, "tenant_id", None),
                endpoint=request.url.path,
                started_at=datetime.utcfromtimestamp(started),
                finished_at=datetime.utcnow(),
                latency_ms=duration_ms,
                http_status=response.status_code,
                request_bytes=len(body),
            )
            db.add(log)
            db.commit()
        finally:
            db.close()
        return response
