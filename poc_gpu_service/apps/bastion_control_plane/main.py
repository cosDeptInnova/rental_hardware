from fastapi import FastAPI
from fastapi.responses import PlainTextResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from shared.config import get_settings
from shared.logging import setup_json_logging
from apps.bastion_control_plane.api.routes import router
from apps.bastion_control_plane.core.bootstrap import init_db_and_seed
from apps.bastion_control_plane.middleware.audit import AuditMiddleware
from apps.bastion_control_plane.middleware.rate_limit import RateLimitMiddleware
from apps.bastion_control_plane.middleware.request_context import RequestContextMiddleware

settings = get_settings()
setup_json_logging("bastion-control-plane", settings.log_level)

app = FastAPI(title="bastion-control-plane", version="0.1.0")
app.add_middleware(RequestContextMiddleware)
app.add_middleware(RateLimitMiddleware, limit_per_minute=settings.rate_limit_per_minute)
app.add_middleware(AuditMiddleware)
app.include_router(router)


@app.on_event("startup")
def startup():
    init_db_and_seed()


@app.get("/metrics")
def metrics():
    return PlainTextResponse(generate_latest().decode("utf-8"), media_type=CONTENT_TYPE_LATEST)
