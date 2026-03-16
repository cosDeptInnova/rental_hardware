from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes_admin import router as admin_router
from app.api.routes_jobs import router as jobs_router
from app.core.db import init_db
from app.scheduler.admission import AdmissionController
from app.supervisor.process_manager import ProcessManager


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    init_db()
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="gpu-broker", version="0.1.0", lifespan=lifespan)

    app.state.process_manager = ProcessManager()
    app.state.admission_controller = AdmissionController()

    @app.get("/health")
    def health() -> dict[str, bool]:
        return {"ok": True}

    app.include_router(admin_router)
    app.include_router(jobs_router)
    return app


app = create_app()
