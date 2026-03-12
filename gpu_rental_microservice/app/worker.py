import asyncio
import uuid

from .config import settings
from .db import (
    init_db, claim_job, get_client_by_name, update_job, insert_job_metric,
    aggregate_job_metrics, mark_job_for_retry, recover_orphan_jobs,
    release_job_lock, heartbeat_job, reconcile_credit_reservation
)
from .job_queue import dequeue_job, promote_delayed_jobs, schedule_retry
from .metering import JOB_GPU_SECONDS
from .redis_control import acquire_global_slot, refresh_global_slot, release_global_slot
from .runner import run_workload


async def _process_job(job: dict, worker_id: str):
    client = get_client_by_name(job["client_name"])
    if not client:
        update_job(job["id"], status="failed", worker_state="failed", execution_error="client not found")
        return

    max_concurrent = int(client["max_concurrent_jobs"])
    if not acquire_global_slot(job["client_name"], job["id"], max_concurrent, settings.worker_slot_lease_seconds):
        retry_delay = 2
        mark_job_for_retry(job["id"], retry_delay, "waiting for global distributed slot")
        schedule_retry(job["id"], retry_delay)
        return

    try:
        heartbeat_job(job["id"], worker_id, settings.worker_lock_seconds)
        refresh_global_slot(job["client_name"], job["id"], settings.worker_slot_lease_seconds)
        result = await run_workload(
            workload_name=job["workload_name"],
            estimated_seconds=int(job["estimated_seconds"]),
            gpu_share=float(client["gpu_share"]),
            max_job_seconds=int(client["max_job_seconds"]),
            max_power_watts=float(client["max_power_watts"]),
            max_energy_joules_per_job=float(client["max_energy_joules_per_job"]),
        )
        for metric in result.metrics:
            insert_job_metric(job_id=job["id"], ts=metric.ts, gpu_util=metric.gpu_util, memory_used_mb=metric.memory_used_mb, power_watts=metric.power_watts, energy_joules=metric.energy_joules)
        aggregated = aggregate_job_metrics(job["id"])
        status = "succeeded" if result.worker_state == "succeeded" else "failed"
        update_job(
            job["id"],
            status=status,
            billed_seconds=result.billed_seconds,
            gpu_seconds=result.gpu_seconds,
            peak_vram_mb=int(aggregated["memory_used_mb"] or result.peak_vram_mb),
            avg_gpu_util=float(aggregated["gpu_util"] or 0.0),
            avg_power_watts=float(aggregated["power_watts"] or 0.0),
            peak_power_watts=float(aggregated["peak_power_watts"] or 0.0),
            energy_joules=float(aggregated["energy_joules"] or 0.0),
            output_bytes=result.output_bytes,
            output_tokens=result.output_tokens,
            worker_state=result.worker_state,
            exit_code=result.exit_code,
            execution_error=result.execution_error,
            finished_at=__import__('datetime').datetime.utcnow().replace(microsecond=0).isoformat(),
        )
        actual_cost = max(float(result.gpu_seconds), 0.0) * float(client["price_per_gpu_second"])
        reconcile_credit_reservation(job["id"], actual_cost)
        if result.gpu_seconds > 0:
            JOB_GPU_SECONDS.labels(job["client_name"], job["workload_name"]).inc(result.gpu_seconds)
    except Exception as exc:
        backoff = min(60, 2 ** (int(job["retry_count"]) + 1))
        can_retry = mark_job_for_retry(job["id"], backoff, str(exc))
        if can_retry:
            schedule_retry(job["id"], backoff)
    finally:
        release_job_lock(job["id"])
        release_global_slot(job["client_name"], job["id"])


async def worker_loop():
    worker_id = f"worker-{uuid.uuid4()}"
    init_db()
    recover_orphan_jobs(settings.orphan_job_timeout_seconds)
    while True:
        promote_delayed_jobs()
        job_id = await asyncio.to_thread(dequeue_job, settings.worker_poll_seconds)
        if not job_id:
            await asyncio.sleep(0.1)
            continue
        job = claim_job(job_id, worker_id, settings.worker_lock_seconds)
        if not job:
            continue
        await _process_job(job, worker_id)


if __name__ == "__main__":
    asyncio.run(worker_loop())
