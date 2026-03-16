from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from app.core.schemas import JobCreate, JobDecision, ReservationCreate, ServiceType
from app.gpu.nvml_monitor import GpuSnapshot


@dataclass
class ManagedWorker:
    worker_id: str
    tenant_id: str | None
    gpu_index: int
    reserved_vram_mb: int
    reclaimable: bool
    priority: int
    busy: bool
    service_type: ServiceType


class AdmissionController:
    def __init__(self, safety_margin_mb: int = 2048):
        self.safety_margin_mb = safety_margin_mb

    def decide(
        self,
        reservation: ReservationCreate,
        request: JobCreate,
        gpu_snapshots: list[GpuSnapshot],
        workers: Iterable[ManagedWorker],
        tenant_active_jobs: int,
    ) -> JobDecision:
        if not reservation.enabled:
            return JobDecision(admitted=False, reason="reservation_disabled")

        if request.service_type not in reservation.allowed_services:
            return JobDecision(admitted=False, reason="service_not_allowed")

        if tenant_active_jobs >= reservation.max_concurrency:
            return JobDecision(admitted=False, reason="concurrency_exceeded")

        reclaimable = sorted(
            [
                w for w in workers
                if w.reclaimable and not w.busy and w.service_type == request.service_type
            ],
            key=lambda x: (x.priority, x.reserved_vram_mb),
        )

        selected_gpu = None
        reclaimed_workers: list[str] = []

        for gpu in gpu_snapshots:
            effective_free = max(gpu.free_mb - self.safety_margin_mb, 0)
            if effective_free >= request.requested_vram_mb:
                selected_gpu = gpu.index
                break

            extra_mb = 0
            local_reclaimed: list[str] = []
            for worker in reclaimable:
                if worker.gpu_index != gpu.index:
                    continue
                extra_mb += worker.reserved_vram_mb
                local_reclaimed.append(worker.worker_id)
                if effective_free + extra_mb >= request.requested_vram_mb:
                    selected_gpu = gpu.index
                    reclaimed_workers = local_reclaimed
                    break

            if selected_gpu is not None:
                break

        if selected_gpu is None:
            return JobDecision(admitted=False, reason="insufficient_capacity")

        return JobDecision(
            admitted=True,
            reason="admitted",
            gpu_index=selected_gpu,
            reclaimed_workers=reclaimed_workers,
        )
