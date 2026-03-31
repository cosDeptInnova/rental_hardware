from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.auth import generate_api_key, hash_api_key, require_admin
from app.core.db import get_db
from sqlalchemy import case, func

from app.core.models import RequestMetric, Reservation, Tenant
from app.core.schemas import (
    AnalyticsServiceBreakdown,
    AnalyticsSummaryRead,
    CapacityRead,
    ReservationCreate,
    ReservationRead,
    ServiceType,
    TenantCreate,
    TenantCreateRead,
)
from app.gpu.nvml_monitor import NvmlMonitor


router = APIRouter(prefix="/v1/admin", tags=["admin"])


@router.post("/tenants", response_model=TenantCreateRead, status_code=status.HTTP_201_CREATED)
def create_tenant(
    payload: TenantCreate,
    _: None = Depends(require_admin),
    db: Session = Depends(get_db),
) -> TenantCreateRead:
    api_key = generate_api_key()
    tenant = Tenant(name=payload.name, api_key_hash=hash_api_key(api_key), status="active")
    db.add(tenant)

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="tenant_already_exists") from None

    db.refresh(tenant)
    return TenantCreateRead(tenant_id=tenant.id, name=tenant.name, api_key=api_key)


@router.post("/reservations", response_model=ReservationRead)
def upsert_reservation(
    payload: ReservationCreate,
    _: None = Depends(require_admin),
    db: Session = Depends(get_db),
) -> ReservationRead:
    tenant = db.get(Tenant, payload.tenant_id)
    if tenant is None:
        raise HTTPException(status_code=404, detail="tenant_not_found")

    existing = db.execute(
        select(Reservation).where(Reservation.tenant_id == payload.tenant_id)
    ).scalar_one_or_none()

    if existing is None:
        existing = Reservation(
            tenant_id=payload.tenant_id,
            reserved_vram_mb=payload.reserved_vram_mb,
            max_concurrency=payload.max_concurrency,
            priority=payload.priority,
            preemptive=payload.preemptive,
            enabled=payload.enabled,
            allowed_services_csv="",
        )
        db.add(existing)

    existing.reserved_vram_mb = payload.reserved_vram_mb
    existing.max_concurrency = payload.max_concurrency
    existing.priority = payload.priority
    existing.preemptive = payload.preemptive
    existing.enabled = payload.enabled
    existing.allowed_services = [x.value for x in payload.allowed_services]

    db.commit()
    db.refresh(existing)

    return ReservationRead(
        id=existing.id,
        tenant_id=existing.tenant_id,
        reserved_vram_mb=existing.reserved_vram_mb,
        max_concurrency=existing.max_concurrency,
        priority=existing.priority,
        allowed_services=payload.allowed_services,
        preemptive=existing.preemptive,
        enabled=existing.enabled,
    )


@router.get("/capacity", response_model=list[CapacityRead])
def capacity(_: None = Depends(require_admin)) -> list[CapacityRead]:
    with NvmlMonitor() as mon:
        if not mon.available:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="nvml_unavailable: NVIDIA NVML no está disponible en este entorno",
            )
        items = mon.snapshots()
    return [CapacityRead(**item.__dict__) for item in items]


@router.get("/analytics/summary", response_model=AnalyticsSummaryRead)
def admin_analytics_summary(
    _: None = Depends(require_admin),
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
        )
    ).one()

    by_service_rows = db.execute(
        select(
            RequestMetric.service_type,
            func.count(RequestMetric.id),
            func.sum(RequestMetric.request_tokens),
            func.sum(RequestMetric.response_tokens),
            func.sum(RequestMetric.total_tokens),
            func.avg(RequestMetric.latency_ms),
        ).group_by(RequestMetric.service_type)
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
        queued_total=0,
        running_total=0,
        finished_total=0,
        failed_jobs_total=0,
        request_tokens_total=int(totals[3] or 0),
        response_tokens_total=int(totals[4] or 0),
        total_tokens_total=int(totals[5] or 0),
        avg_latency_ms=float(totals[6] or 0),
        by_service=by_service,
    )
