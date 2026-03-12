import time
import uuid
from datetime import datetime

from fastapi import FastAPI, Depends, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST

from .config import settings
from .db import (
    init_db, get_job,
    count_running_jobs, insert_audit, monthly_usage, utcnow_iso, recover_orphan_jobs,
    create_job_with_reservation, ReservationError
)
from .deps import require_scope
from .job_queue import enqueue_job
from .limiting import rate_limiter
from .metering import REQUESTS, REQUEST_LATENCY
from .models import JobCreate, JobPublic, UsagePublic
from .redis_control import acquire_client_submission_lock, release_client_submission_lock
from .routers.admin import router as admin_router

app = FastAPI(
    title=settings.app_name,
    docs_url="/docs" if settings.docs_enabled else None,
    redoc_url="/redoc" if settings.docs_enabled else None,
)

app.include_router(admin_router)


@app.on_event("startup")
def startup():
    init_db()
    recover_orphan_jobs(settings.orphan_job_timeout_seconds)


@app.middleware("http")
async def audit_and_security_middleware(request: Request, call_next):
    start = time.perf_counter()
    request_id = str(uuid.uuid4())
    request.state.request_id = request_id

    client_name = getattr(request.state, "authenticated_client_name", "anonymous")
    response = None
    try:
        response = await call_next(request)
    except Exception:
        response = JSONResponse(status_code=500, content={"detail": "Internal server error"})
        raise
    finally:
        latency_ms = round((time.perf_counter() - start) * 1000, 2)
        client_name = getattr(request.state, "authenticated_client_name", client_name)
        response_bytes = len(getattr(response, "body", b"") or b"")
        request_bytes = int(request.headers.get("content-length", "0") or "0")
        insert_audit(
            client_name=client_name,
            path=request.url.path,
            method=request.method,
            status_code=response.status_code,
            event_type="request",
            event_detail=getattr(request.state, "auth_type", None),
            request_bytes=request_bytes,
            response_bytes=response_bytes,
            latency_ms=latency_ms,
            created_at=utcnow_iso(),
        )
        REQUESTS.labels(client_name, request.url.path, request.method, str(response.status_code)).inc()
        REQUEST_LATENCY.labels(client_name, request.url.path, request.method).observe(latency_ms / 1000.0)
        response.headers["X-Request-ID"] = request_id
        if settings.secure_headers:
            response.headers["X-Content-Type-Options"] = "nosniff"
            response.headers["X-Frame-Options"] = "DENY"
            response.headers["Referrer-Policy"] = "no-referrer"
            response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/healthz")
def healthz():
    return {"status": "ok", "service": settings.app_name}


@app.get("/metrics")
def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


def _estimate_tokens(raw_bytes: int) -> int:
    return max(0, raw_bytes // 4)


@app.post("/v1/jobs", response_model=JobPublic, status_code=status.HTTP_202_ACCEPTED)
async def create_job(payload: JobCreate, request: Request, client=Depends(require_scope("jobs:write"))):
    client_name = client["client_name"]
    api_key_hash = getattr(request.state, "api_key_hash", client_name)

    rpm = int(client["requests_per_minute"])
    if not rate_limiter.allow(f"{client_name}:{api_key_hash}:rpm", limit=rpm, window_seconds=60):
        raise HTTPException(status_code=429, detail="Rate limit exceeded")

    if payload.estimated_seconds > int(client["max_job_seconds"]):
        raise HTTPException(status_code=400, detail="estimated_seconds exceeds contract limit")
    if payload.input_bytes > int(client["max_input_bytes"]):
        raise HTTPException(status_code=400, detail="input_bytes exceeds contract limit")
    if count_running_jobs(client_name) >= int(client["max_concurrent_jobs"]):
        raise HTTPException(status_code=429, detail="Too many concurrent jobs")

    estimated_input_tokens = _estimate_tokens(payload.input_bytes)
    if estimated_input_tokens > int(client["max_tokens_per_job"]):
        raise HTTPException(status_code=400, detail="estimated input tokens exceed max_tokens_per_job")

    month = datetime.utcnow().strftime("%Y-%m")
    _, client_row = monthly_usage(client_name, month)
    projected_gpu_seconds = payload.estimated_seconds * payload.gpu_share
    projected_gpu_cost = projected_gpu_seconds * float(client_row["price_per_gpu_second"])

    job_id = str(uuid.uuid4())
    row = {
        "id": job_id,
        "client_name": client_name,
        "workload_name": payload.workload_name,
        "status": "queued",
        "estimated_seconds": payload.estimated_seconds,
        "billed_seconds": 0,
        "gpu_seconds": 0.0,
        "peak_vram_mb": 0,
        "input_bytes": payload.input_bytes,
        "output_bytes": 0,
        "input_tokens": estimated_input_tokens,
        "output_tokens": 0,
        "idempotency_key": payload.idempotency_key,
        "created_at": utcnow_iso(),
        "started_at": None,
        "finished_at": None,
        "worker_state": "queued",
        "exit_code": None,
        "execution_error": None,
        "avg_gpu_util": 0.0,
        "avg_power_watts": 0.0,
        "peak_power_watts": 0.0,
        "energy_joules": 0.0,
        "retry_count": 0,
        "max_retries": settings.default_job_max_retries,
        "next_retry_at": None,
        "locked_by": None,
        "lock_expires_at": None,
        "last_heartbeat": None,
    }
    lock_token = str(uuid.uuid4())
    has_submission_lock = acquire_client_submission_lock(client_name, lock_token, ttl_seconds=10)
    if not has_submission_lock:
        raise HTTPException(status_code=409, detail="Concurrent submission in progress, retry")

    try:
        stored, created = create_job_with_reservation(
            job=row,
            projected_cost=projected_gpu_cost,
            estimated_input_tokens=estimated_input_tokens,
            month_prefix=month,
        )
    except ReservationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    finally:
        release_client_submission_lock(client_name, lock_token)

    if created:
        enqueue_job(job_id)
    return stored


@app.get("/v1/jobs/{job_id}", response_model=JobPublic)
def get_job_status(job_id: str, client=Depends(require_scope("jobs:read"))):
    row = get_job(job_id)
    if not row:
        raise HTTPException(status_code=404, detail="Job not found")
    if row["client_name"] != client["client_name"] and not client["is_admin"]:
        raise HTTPException(status_code=403, detail="Forbidden")
    return dict(row)


@app.get("/v1/usage/me", response_model=UsagePublic)
def get_my_usage(client=Depends(require_scope("usage:read"))):
    month = datetime.utcnow().strftime("%Y-%m")
    usage, client_row = monthly_usage(client["client_name"], month)
    total_tokens = int(usage["total_input_tokens"] or 0) + int(usage["total_output_tokens"] or 0)
    total_kwh = float(usage["total_energy_joules"] or 0) / 3_600_000.0

    gpu_cost = round(float(usage["total_gpu_seconds"] or 0) * float(client_row["price_per_gpu_second"]), 4)
    token_cost = round((total_tokens / 1000.0) * settings.price_per_1k_tokens, 4)
    energy_cost = round(total_kwh * settings.price_per_kwh, 4)
    estimated_cost = round(gpu_cost + token_cost + energy_cost, 4)

    return {
        "client_name": client["client_name"],
        "month": month,
        "total_requests": int(usage["total_requests"] or 0),
        "total_input_bytes": int(usage["total_input_bytes"] or 0),
        "total_output_bytes": int(usage["total_output_bytes"] or 0),
        "total_billed_seconds": int(usage["total_billed_seconds"] or 0),
        "total_gpu_seconds": float(usage["total_gpu_seconds"] or 0),
        "total_peak_vram_mb": int(usage["total_peak_vram_mb"] or 0),
        "total_input_tokens": int(usage["total_input_tokens"] or 0),
        "total_output_tokens": int(usage["total_output_tokens"] or 0),
        "total_energy_joules": float(usage["total_energy_joules"] or 0),
        "gpu_cost": gpu_cost,
        "token_cost": token_cost,
        "energy_cost": energy_cost,
        "estimated_cost": estimated_cost,
        "currency": settings.default_currency,
    }
