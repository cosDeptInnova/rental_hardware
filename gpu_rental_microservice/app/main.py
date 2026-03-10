import asyncio
import math
import uuid
import time
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, Depends, HTTPException, Request, Response, status
from fastapi.responses import PlainTextResponse, JSONResponse
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST

from .config import settings
from .db import (
    init_db, insert_job, get_job, get_job_by_idempotency, update_job,
    count_running_jobs, insert_audit, monthly_usage, list_clients, utcnow_iso
)
from .deps import get_current_client, require_scope, require_admin
from .limiting import rate_limiter
from .metering import REQUESTS, REQUEST_LATENCY, JOB_GPU_SECONDS, RUNNING_JOBS
from .models import JobCreate, JobPublic, UsagePublic

app = FastAPI(
    title=settings.app_name,
    docs_url="/docs" if settings.docs_enabled else None,
    redoc_url="/redoc" if settings.docs_enabled else None,
)

@app.on_event("startup")
def startup():
    init_db()

@app.middleware("http")
async def audit_and_security_middleware(request: Request, call_next):
    start = time.perf_counter()
    request_id = str(uuid.uuid4())
    request.state.request_id = request_id

    client_name = "anonymous"
    try:
        response = await call_next(request)
    except Exception:
        response = JSONResponse(status_code=500, content={"detail": "Internal server error"})
        raise
    finally:
        latency_ms = round((time.perf_counter() - start) * 1000, 2)
        x_api_key = request.headers.get("X-API-Key")
        if x_api_key:
            # No lookup here to keep middleware lightweight; keep anonymous if auth fails before dependency.
            client_name = request.headers.get("X-Client-Name", "authenticated")
        response_bytes = len(getattr(response, "body", b"") or b"")
        request_bytes = int(request.headers.get("content-length", "0") or "0")
        insert_audit(
            client_name=client_name,
            path=request.url.path,
            method=request.method,
            status_code=response.status_code,
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

async def _run_job(job_id: str, estimated_seconds: int, client_name: str, workload_name: str, gpu_share: float):
    update_job(job_id, status="running", started_at=utcnow_iso())
    RUNNING_JOBS.labels(client_name).inc()
    try:
        await asyncio.sleep(min(estimated_seconds, 10))
        billed_seconds = min(estimated_seconds, 10)
        gpu_seconds = billed_seconds * gpu_share
        peak_vram_mb = int(4000 + (gpu_share * 8000))
        output_bytes = int(estimated_seconds * 1500)
        update_job(
            job_id,
            status="succeeded",
            billed_seconds=billed_seconds,
            gpu_seconds=gpu_seconds,
            peak_vram_mb=peak_vram_mb,
            output_bytes=output_bytes,
            finished_at=utcnow_iso(),
        )
        JOB_GPU_SECONDS.labels(client_name, workload_name).inc(gpu_seconds)
    except Exception:
        update_job(job_id, status="failed", finished_at=utcnow_iso())
    finally:
        RUNNING_JOBS.labels(client_name).dec()

@app.post("/v1/jobs", response_model=JobPublic, status_code=status.HTTP_202_ACCEPTED)
async def create_job(payload: JobCreate, request: Request, client = Depends(require_scope("jobs:write"))):
    client_name = client["client_name"]

    # 1) Rate limit
    rpm = int(client["requests_per_minute"])
    if not rate_limiter.allow(f"{client_name}:rpm", limit=rpm, window_seconds=60):
        raise HTTPException(status_code=429, detail="Rate limit exceeded")

    # 2) Contract limits
    if payload.estimated_seconds > int(client["max_job_seconds"]):
        raise HTTPException(status_code=400, detail="estimated_seconds exceeds contract limit")
    if payload.input_bytes > int(client["max_input_bytes"]):
        raise HTTPException(status_code=400, detail="input_bytes exceeds contract limit")
    if count_running_jobs(client_name) >= int(client["max_concurrent_jobs"]):
        raise HTTPException(status_code=429, detail="Too many concurrent jobs")

    # 3) Idempotency
    existing = get_job_by_idempotency(client_name, payload.idempotency_key)
    if existing:
        return dict(existing)

    # 4) Monthly credit limit guard
    month = datetime.utcnow().strftime("%Y-%m")
    usage, client_row = monthly_usage(client_name, month)
    projected_gpu_seconds = payload.estimated_seconds * payload.gpu_share
    projected_cost = float(usage["total_gpu_seconds"] or 0) * float(client_row["price_per_gpu_second"])
    projected_cost += projected_gpu_seconds * float(client_row["price_per_gpu_second"])
    if projected_cost > float(client_row["monthly_credit_limit"]):
        raise HTTPException(status_code=402, detail="Monthly credit limit exceeded")

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
        "idempotency_key": payload.idempotency_key,
        "created_at": utcnow_iso(),
        "started_at": None,
        "finished_at": None,
    }
    insert_job(row)
    asyncio.create_task(
        _run_job(
            job_id=job_id,
            estimated_seconds=payload.estimated_seconds,
            client_name=client_name,
            workload_name=payload.workload_name,
            gpu_share=payload.gpu_share,
        )
    )
    return row

@app.get("/v1/jobs/{job_id}", response_model=JobPublic)
def get_job_status(job_id: str, client = Depends(require_scope("jobs:read"))):
    row = get_job(job_id)
    if not row:
        raise HTTPException(status_code=404, detail="Job not found")
    if row["client_name"] != client["client_name"] and not client["is_admin"]:
        raise HTTPException(status_code=403, detail="Forbidden")
    return dict(row)

@app.get("/v1/usage/me", response_model=UsagePublic)
def get_my_usage(client = Depends(require_scope("usage:read"))):
    month = datetime.utcnow().strftime("%Y-%m")
    usage, client_row = monthly_usage(client["client_name"], month)
    estimated_cost = round(
        float(usage["total_gpu_seconds"] or 0) * float(client_row["price_per_gpu_second"]),
        4,
    )
    return {
        "client_name": client["client_name"],
        "month": month,
        "total_requests": int(usage["total_requests"] or 0),
        "total_input_bytes": int(usage["total_input_bytes"] or 0),
        "total_output_bytes": int(usage["total_output_bytes"] or 0),
        "total_billed_seconds": int(usage["total_billed_seconds"] or 0),
        "total_gpu_seconds": float(usage["total_gpu_seconds"] or 0),
        "total_peak_vram_mb": int(usage["total_peak_vram_mb"] or 0),
        "estimated_cost": estimated_cost,
        "currency": settings.default_currency,
    }

@app.get("/v1/admin/clients")
def admin_clients(_ = Depends(require_admin)):
    return [dict(r) for r in list_clients()]
