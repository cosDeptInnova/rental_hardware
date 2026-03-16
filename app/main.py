from __future__ import annotations

from fastapi import FastAPI

from app.api.routes_admin import router as admin_router
from app.api.routes_jobs import router as jobs_router
from app.core.db import init_db
from app.scheduler.admission import AdmissionController
from app.supervisor.process_manager import ProcessManager


def create_app() -> FastAPI:
    app = FastAPI(title="gpu-broker", version="0.1.0")

    app.state.process_manager = ProcessManager()
    app.state.admission_controller = AdmissionController()

    @app.on_event("startup")
    def startup() -> None:
        init_db()

    @app.get("/health")
    def health() -> dict[str, bool]:
        return {"ok": True}

    app.include_router(admin_router)
    app.include_router(jobs_router)
    return app


app = create_app()
