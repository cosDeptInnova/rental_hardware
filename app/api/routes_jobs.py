from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.auth import get_current_tenant
from app.core.db import get_db
from app.core.models import Job, Reservation, Tenant
from app.core.schemas import JobCreate, JobRead, ReservationCreate, ServiceType
from app.gpu.nvml_monitor import NvmlMonitor
from app.scheduler.admission import AdmissionController
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


@router.post("/jobs", response_model=JobRead)
def submit_job(
    payload: JobCreate,
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
    process_manager: ProcessManager = Depends(get_process_manager),
    admission: AdmissionController = Depends(get_admission_controller),
) -> JobRead:
    reservation = db.execute(
        select(Reservation).where(Reservation.tenant_id == tenant.id)
    ).scalar_one_or_none()

    if reservation is None:
        raise HTTPException(status_code=403, detail="tenant_has_no_reservation")

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
        payload_json=payload.payload,
        state="queued",
        error=None,
    )
    db.add(job)
    db.commit()
    db.refresh(job)

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
