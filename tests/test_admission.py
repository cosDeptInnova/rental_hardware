from app.core.schemas import JobCreate, ReservationCreate, ServiceType
from app.gpu.nvml_monitor import GpuSnapshot
from app.scheduler.admission import AdmissionController, ManagedWorker


def test_admits_when_enough_free_capacity() -> None:
    controller = AdmissionController(safety_margin_mb=1024)

    reservation = ReservationCreate(
        tenant_id="t1",
        reserved_vram_mb=8192,
        max_concurrency=2,
        priority=90,
        allowed_services=[ServiceType.INFERENCE],
        preemptive=True,
        enabled=True,
    )

    request = JobCreate(
        service_type=ServiceType.INFERENCE,
        requested_vram_mb=4096,
        priority=50,
        payload={},
    )

    snapshots = [
        GpuSnapshot(
            index=0,
            name="L40S",
            uuid="gpu-0",
            total_mb=49152,
            used_mb=20000,
            free_mb=28000,
            gpu_util=40,
            processes=[],
        )
    ]

    decision = controller.decide(
        reservation=reservation,
        request=request,
        gpu_snapshots=snapshots,
        workers=[],
        tenant_active_jobs=0,
    )

    assert decision.admitted is True
    assert decision.gpu_index == 0
    assert decision.reclaimed_workers == []


def test_reclaims_workers_when_free_capacity_is_not_enough() -> None:
    controller = AdmissionController(safety_margin_mb=1024)

    reservation = ReservationCreate(
        tenant_id="t1",
        reserved_vram_mb=16384,
        max_concurrency=2,
        priority=90,
        allowed_services=[ServiceType.INFERENCE],
        preemptive=True,
        enabled=True,
    )

    request = JobCreate(
        service_type=ServiceType.INFERENCE,
        requested_vram_mb=12000,
        priority=50,
        payload={},
    )

    snapshots = [
        GpuSnapshot(
            index=0,
            name="L40S",
            uuid="gpu-0",
            total_mb=49152,
            used_mb=42000,
            free_mb=5000,
            gpu_util=90,
            processes=[],
        )
    ]

    workers = [
        ManagedWorker(
            worker_id="w1",
            tenant_id=None,
            gpu_index=0,
            reserved_vram_mb=4096,
            reclaimable=True,
            priority=10,
            busy=False,
            service_type=ServiceType.INFERENCE,
        ),
        ManagedWorker(
            worker_id="w2",
            tenant_id=None,
            gpu_index=0,
            reserved_vram_mb=4096,
            reclaimable=True,
            priority=20,
            busy=False,
            service_type=ServiceType.INFERENCE,
        ),
    ]

    decision = controller.decide(
        reservation=reservation,
        request=request,
        gpu_snapshots=snapshots,
        workers=workers,
        tenant_active_jobs=0,
    )

    assert decision.admitted is True
    assert decision.gpu_index == 0
    assert decision.reclaimed_workers == ["w1", "w2"]
