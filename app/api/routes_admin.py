from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.auth import require_admin
from app.core.db import get_db
from app.core.models import Reservation, Tenant
from app.core.schemas import CapacityRead, ReservationCreate, ReservationRead
from app.gpu.nvml_monitor import NvmlMonitor


router = APIRouter(prefix="/v1/admin", tags=["admin"])


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
        items = mon.snapshots()
    return [CapacityRead(**item.__dict__) for item in items]
