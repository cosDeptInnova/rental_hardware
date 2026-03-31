from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.core.auth import get_current_tenant
from app.core.db import get_db
from app.core.models import Job, RequestMetric, Reservation, Tenant, TenantQuota
from app.core.schemas import (
    AnalyticsServiceBreakdown,
    AnalyticsSummaryRead,
    EmbeddingsRequest,
    InferenceRequest,
    JobCreate,
    JobRead,
    ReservationCreate,
    ServiceResponse,
    ServiceType,
)
from app.gpu.nvml_monitor import NvmlMonitor
from app.scheduler.admission import AdmissionController
from app.services.llama_gateway import LlamaGateway
from app.supervisor.process_manager import ProcessManager


router = APIRouter(prefix="/v1", tags=["jobs"])


def get_process_manager(request: Request) -> ProcessManager:
    return request.app.state.process_manager


def get_admission_controller(request: Request) -> AdmissionController:
    return request.app.state.admission_controller


def reservation_model_to_schema(reservation: Reservation) -> ReservationCreate:
    return ReservationCreate(
        tenant_id=reservation.tenant_id,
        reserved_vram_mb=reservation.reserved_vram_mb,
        max_concurrency=reservation.max_concurrency,
        priority=reservation.priority,
        allowed_services=[ServiceType(x) for x in reservation.allowed_services],
        preemptive=reservation.preemptive,
        enabled=reservation.enabled,
    )


def _create_job(
    payload: JobCreate,
    tenant: Tenant,
    db: Session,
    process_manager: ProcessManager,
    admission: AdmissionController,
) -> Job:
    reservation = db.execute(
        select(Reservation).where(Reservation.tenant_id == tenant.id)
    ).scalar_one_or_none()

    if reservation is None:
        raise HTTPException(status_code=403, detail="tenant_has_no_reservation")

    quota = db.execute(select(TenantQuota).where(TenantQuota.tenant_id == tenant.id)).scalar_one_or_none()
    if quota is not None:
        now = datetime.now(timezone.utc)
        day_start = datetime(now.year, now.month, now.day, tzinfo=timezone.utc)
        month_start = datetime(now.year, now.month, 1, tzinfo=timezone.utc)

        reqs_day = db.execute(
            select(func.count(RequestMetric.id)).where(
                RequestMetric.tenant_id == tenant.id,
                RequestMetric.created_at >= day_start,
            )
        ).scalar_one()
        reqs_month = db.execute(
            select(func.count(RequestMetric.id)).where(
                RequestMetric.tenant_id == tenant.id,
                RequestMetric.created_at >= month_start,
            )
        ).scalar_one()
        tokens_day = db.execute(
            select(func.sum(RequestMetric.total_tokens)).where(
                RequestMetric.tenant_id == tenant.id,
                RequestMetric.created_at >= day_start,
            )
        ).scalar_one()
        tokens_month = db.execute(
            select(func.sum(RequestMetric.total_tokens)).where(
                RequestMetric.tenant_id == tenant.id,
                RequestMetric.created_at >= month_start,
            )
        ).scalar_one()

        if quota.requests_per_day > 0 and int(reqs_day or 0) >= quota.requests_per_day:
            raise HTTPException(status_code=429, detail="quota_requests_per_day_exceeded")
        if quota.requests_per_month > 0 and int(reqs_month or 0) >= quota.requests_per_month:
            raise HTTPException(status_code=429, detail="quota_requests_per_month_exceeded")
        estimated_tokens = max(len(str(payload.payload)) // 4, 1)
        if quota.tokens_per_day > 0 and int(tokens_day or 0) + estimated_tokens > quota.tokens_per_day:
            raise HTTPException(status_code=429, detail="quota_tokens_per_day_exceeded")
        if quota.tokens_per_month > 0 and int(tokens_month or 0) + estimated_tokens > quota.tokens_per_month:
            raise HTTPException(status_code=429, detail="quota_tokens_per_month_exceeded")

    active_jobs = db.execute(
        select(func.count(Job.id)).where(
            Job.tenant_id == tenant.id,
            Job.state.in_(["queued", "running"]),
        )
    ).scalar_one()

    with NvmlMonitor() as mon:
        gpu_snapshots = mon.snapshots()

    decision = admission.decide(
        reservation=reservation_model_to_schema(reservation),
        request=payload,
        gpu_snapshots=gpu_snapshots,
        workers=process_manager.list_workers(),
        tenant_active_jobs=int(active_jobs or 0),
    )

    if not decision.admitted:
        raise HTTPException(status_code=429, detail=decision.reason)

    if decision.reclaimed_workers:
        process_manager.reclaim(decision.reclaimed_workers)

    job = Job(
        tenant_id=tenant.id,
        service_type=payload.service_type.value,
        requested_vram_mb=payload.requested_vram_mb,
        priority=payload.priority,
        payload_json={**payload.payload, "_model": payload.model},
        state="queued",
        error=None,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


@router.post("/jobs", response_model=JobRead)
def submit_job(
    payload: JobCreate,
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
    process_manager: ProcessManager = Depends(get_process_manager),
    admission: AdmissionController = Depends(get_admission_controller),
) -> JobRead:
    job = _create_job(
        payload=payload,
        tenant=tenant,
        db=db,
        process_manager=process_manager,
        admission=admission,
    )

    return JobRead(
        id=job.id,
        external_id=job.external_id,
        tenant_id=job.tenant_id,
        service_type=ServiceType(job.service_type),
        requested_vram_mb=job.requested_vram_mb,
        priority=job.priority,
        state=job.state,
        worker_id=job.worker_id,
        error=job.error,
    )


def _execute_service(
    service_type: ServiceType,
    model_name: str,
    requested_vram_mb: int,
    priority: int,
    payload: dict,
    endpoint: str,
    tenant: Tenant,
    db: Session,
    process_manager: ProcessManager,
    admission: AdmissionController,
) -> ServiceResponse:
    created_job = _create_job(
        payload=JobCreate(
            service_type=service_type,
            requested_vram_mb=requested_vram_mb,
            priority=priority,
            payload=payload,
            model=model_name,
        ),
        tenant=tenant,
        db=db,
        process_manager=process_manager,
        admission=admission,
    )

    created_job.state = "running"
    db.commit()
    db.refresh(created_job)

    result = LlamaGateway().invoke(service_type=service_type, model_name=model_name, payload=payload)
    created_job.state = "finished" if result.ok else "failed"
    created_job.error = result.error
    db.add(
        RequestMetric(
            tenant_id=tenant.id,
            job_id=created_job.id,
            service_type=service_type.value,
            endpoint=endpoint,
            model_name=model_name,
            status_code=result.status_code,
            state=created_job.state,
            request_tokens=result.request_tokens,
            response_tokens=result.response_tokens,
            total_tokens=result.request_tokens + result.response_tokens,
            latency_ms=result.latency_ms,
            error=result.error,
        )
    )
    db.commit()

    return ServiceResponse(
        request_id=created_job.external_id,
        job_id=created_job.id,
        state=created_job.state,
        status_code=result.status_code,
        service_type=service_type,
        model=model_name,
        result=result.output,
    )


@router.post("/inference", response_model=ServiceResponse)
def run_inference(
    payload: InferenceRequest,
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
    process_manager: ProcessManager = Depends(get_process_manager),
    admission: AdmissionController = Depends(get_admission_controller),
) -> ServiceResponse:
    return _execute_service(
        service_type=ServiceType.INFERENCE,
        model_name=payload.model,
        requested_vram_mb=payload.requested_vram_mb,
        priority=payload.priority,
        payload=payload.payload,
        endpoint="/v1/inference",
        tenant=tenant,
        db=db,
        process_manager=process_manager,
        admission=admission,
    )


@router.post("/embeddings", response_model=ServiceResponse)
def run_embeddings(
    payload: EmbeddingsRequest,
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
    process_manager: ProcessManager = Depends(get_process_manager),
    admission: AdmissionController = Depends(get_admission_controller),
) -> ServiceResponse:
    return _execute_service(
        service_type=ServiceType.EMBEDDINGS,
        model_name=payload.model,
        requested_vram_mb=payload.requested_vram_mb,
        priority=payload.priority,
        payload=payload.payload,
        endpoint="/v1/embeddings",
        tenant=tenant,
        db=db,
        process_manager=process_manager,
        admission=admission,
    )


@router.get("/jobs/{job_id}", response_model=JobRead)
def get_job(
    job_id: str,
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
) -> JobRead:
    job = db.execute(
        select(Job).where(Job.external_id == job_id, Job.tenant_id == tenant.id)
    ).scalar_one_or_none()

    if job is None:
        raise HTTPException(status_code=404, detail="job_not_found")

    return JobRead(
        id=job.id,
        external_id=job.external_id,
        tenant_id=job.tenant_id,
        service_type=ServiceType(job.service_type),
        requested_vram_mb=job.requested_vram_mb,
        priority=job.priority,
        state=job.state,
        worker_id=job.worker_id,
        error=job.error,
    )


@router.get("/analytics/summary", response_model=AnalyticsSummaryRead)
def analytics_summary(
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
) -> AnalyticsSummaryRead:
    totals = db.execute(
        select(
            func.count(RequestMetric.id),
            func.sum(case((RequestMetric.status_code < 400, 1), else_=0)),
            func.sum(case((RequestMetric.status_code >= 400, 1), else_=0)),
            func.sum(RequestMetric.request_tokens),
            func.sum(RequestMetric.response_tokens),
            func.sum(RequestMetric.total_tokens),
            func.avg(RequestMetric.latency_ms),
        ).where(RequestMetric.tenant_id == tenant.id)
    ).one()

    job_totals = db.execute(
        select(
            func.sum(case((Job.state == "queued", 1), else_=0)),
            func.sum(case((Job.state == "running", 1), else_=0)),
            func.sum(case((Job.state == "finished", 1), else_=0)),
            func.sum(case((Job.state == "failed", 1), else_=0)),
        ).where(Job.tenant_id == tenant.id)
    ).one()

    by_service_rows = db.execute(
        select(
            RequestMetric.service_type,
            func.count(RequestMetric.id),
            func.sum(RequestMetric.request_tokens),
            func.sum(RequestMetric.response_tokens),
            func.sum(RequestMetric.total_tokens),
            func.avg(RequestMetric.latency_ms),
        )
        .where(RequestMetric.tenant_id == tenant.id)
        .group_by(RequestMetric.service_type)
    ).all()
    by_state_rows = db.execute(
        select(RequestMetric.state, func.count(RequestMetric.id))
        .where(RequestMetric.tenant_id == tenant.id)
        .group_by(RequestMetric.state)
    ).all()

    by_service = [
        AnalyticsServiceBreakdown(
            service_type=ServiceType(row[0]),
            requests=int(row[1] or 0),
            request_tokens=int(row[2] or 0),
            response_tokens=int(row[3] or 0),
            total_tokens=int(row[4] or 0),
            avg_latency_ms=float(row[5] or 0),
        )
        for row in by_service_rows
    ]

    return AnalyticsSummaryRead(
        requests_total=int(totals[0] or 0),
        success_total=int(totals[1] or 0),
        failed_total=int(totals[2] or 0),
        queued_total=int(job_totals[0] or 0),
        running_total=int(job_totals[1] or 0),
        finished_total=int(job_totals[2] or 0),
        failed_jobs_total=int(job_totals[3] or 0),
        request_tokens_total=int(totals[3] or 0),
        response_tokens_total=int(totals[4] or 0),
        total_tokens_total=int(totals[5] or 0),
        avg_latency_ms=float(totals[6] or 0),
        by_service=by_service,
        by_state={str(row[0]): int(row[1] or 0) for row in by_state_rows},
    )
