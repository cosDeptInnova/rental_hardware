from fastapi import FastAPI
from fastapi.responses import PlainTextResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from shared.config import get_settings
from shared.logging import setup_json_logging
from apps.gpu_agent.api.routes import router
from apps.gpu_agent.core.bootstrap import init_db
from apps.gpu_agent.middleware.request_context import RequestContextMiddleware

settings = get_settings()
setup_json_logging("gpu-agent", settings.log_level)

app = FastAPI(title="gpu-agent", version="0.1.0")
app.add_middleware(RequestContextMiddleware)
app.include_router(router)


@app.on_event("startup")
def startup():
    init_db()


@app.get("/metrics")
def metrics():
    return PlainTextResponse(generate_latest().decode("utf-8"), media_type=CONTENT_TYPE_LATEST)
