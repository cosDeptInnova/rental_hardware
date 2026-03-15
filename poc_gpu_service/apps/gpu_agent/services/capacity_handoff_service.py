import json
import logging
import re
import uuid
from datetime import datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from apps.gpu_agent.models.db_models import BackendInstance, GpuStateSnapshot, HandoffEvent
from apps.gpu_agent.services.backend_service import stop_backend, start_backend
from apps.gpu_agent.services.metrics_service import collect_gpu_metrics
from shared.config import get_settings


logger = logging.getLogger(__name__)


def _to_json(data: dict) -> str:
    return json.dumps(data, ensure_ascii=False)


def _log_event(db: Session, action_type: str, success: bool, details: dict, lease_id: str | None = None, tenant_id: str | None = None) -> None:
    db.add(
        HandoffEvent(
            timestamp=datetime.utcnow(),
            lease_id=lease_id,
            tenant_id=tenant_id,
            action_type=action_type,
            success=success,
            details_json=_to_json(details),
        )
    )
    db.commit()


def _gpu0_status_payload() -> dict:
    settings = get_settings()
    metrics = collect_gpu_metrics()
    gpu = next((g for g in metrics.get("gpus", []) if str(g.get("index")) == "0"), None)
    if not gpu:
        raise RuntimeError("GPU0 not found in nvidia-smi output")

    total = int(gpu.get("memory_total_mib", 0))
    used = int(gpu.get("memory_used_mib", 0))
    free = max(total - used, 0)
    target = settings.client_gpu0_target_free_vram_mib
    safety = settings.client_gpu0_safety_margin_mib
    required = target + safety
    return {
        "timestamp": metrics.get("timestamp"),
        "gpu_index": 0,
        "memory_total_mib": total,
        "memory_used_mib": used,
        "memory_free_mib": free,
        "target_free_vram_mib": target,
        "safety_margin_mib": safety,
        "required_free_vram_mib": required,
        "target_satisfiable": free >= required,
        "compute_apps": [a for a in metrics.get("compute_apps", []) if str(a.get("gpu_index", "0")) == "0"],
    }


def _process_index_by_pid(compute_apps: list[dict]) -> dict[int, dict]:
    out: dict[int, dict] = {}
    for app in compute_apps:
        pid = app.get("pid")
        if isinstance(pid, int):
            out[pid] = app
    return out


def create_snapshot(db: Session, lease_id: str | None = None, tenant_id: str | None = None, notes: str | None = None, request_id: str | None = None) -> dict:
    status = _gpu0_status_payload()
    pid_map = _process_index_by_pid(status.get("compute_apps", []))
    managed = db.scalars(select(BackendInstance).where(BackendInstance.gpu_device == "CUDA0")).all()

    backends = []
    for item in managed:
        cmd = []
        try:
            cmd = json.loads(item.extra_json or "{}").get("command", [])
        except Exception:
            pass
        backends.append(
            {
                "instance_id": item.instance_id,
                "tenant_id": item.tenant_id,
                "model_alias": item.model_alias,
                "status": item.status,
                "gpu_device": item.gpu_device,
                "pid": item.pid,
                "port": item.port,
                "command": cmd,
                "drainable": item.drainable,
                "critical": item.critical,
                "service_tier": item.service_tier,
                "restore_priority": item.restore_priority,
                "vram_mib": int(pid_map.get(item.pid or -1, {}).get("used_gpu_memory_mib", 0)),
                "created_at": item.created_at.isoformat() if item.created_at else None,
            }
        )

    payload = {
        "timestamp": status["timestamp"],
        "gpu_index": 0,
        "gpu_status": status,
        "processes_gpu0": status.get("compute_apps", []),
        "backends_known": backends,
        "metadata": {"lease_id": lease_id, "tenant_id": tenant_id, "request_id": request_id},
    }
    snapshot_id = str(uuid.uuid4())
    Path("state").mkdir(exist_ok=True)
    snapshot_path = Path("state") / f"gpu0_snapshot_{snapshot_id}.json"
    snapshot_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    rec = GpuStateSnapshot(
        snapshot_id=snapshot_id,
        created_at=datetime.utcnow(),
        lease_id=lease_id,
        tenant_id=tenant_id,
        gpu_index=0,
        snapshot_json=_to_json(payload),
        notes=notes,
    )
    db.add(rec)
    db.commit()
    _log_event(db, "snapshot", True, {"snapshot_id": snapshot_id, "path": str(snapshot_path)}, lease_id=lease_id, tenant_id=tenant_id)
    logger.info("gpu0_snapshot_created", extra={"extra": {"request_id": request_id, "lease_id": lease_id, "snapshot_id": snapshot_id}})
    return {"snapshot_id": snapshot_id, "path": str(snapshot_path), "snapshot": payload}


def _is_non_drainable_name(name: str) -> bool:
    patterns = [p.strip() for p in get_settings().non_drainable_process_patterns.split(",") if p.strip()]
    return any(re.search(pattern, name, re.IGNORECASE) for pattern in patterns)


def _candidate_priority(instance: BackendInstance, alias_counts: dict[str, int]) -> tuple[int, int]:
    if instance.drainable and instance.service_tier == "production_replicas":
        return (1, instance.restore_priority)
    if instance.tenant_id == "interno" and not instance.critical:
        return (2, instance.restore_priority)
    if alias_counts.get(instance.model_alias, 0) > 1:
        return (3, instance.restore_priority)
    return (99, instance.restore_priority)


def select_drain_candidates(db: Session) -> list[dict]:
    running = db.scalars(
        select(BackendInstance).where(BackendInstance.status == "running", BackendInstance.gpu_device == "CUDA0")
    ).all()
    alias_counts: dict[str, int] = {}
    for item in running:
        alias_counts[item.model_alias] = alias_counts.get(item.model_alias, 0) + 1

    candidates: list[tuple[tuple[int, int], BackendInstance]] = []
    for item in running:
        if item.critical:
            continue
        if not item.drainable and alias_counts.get(item.model_alias, 0) <= 1 and item.tenant_id != "interno":
            continue
        if _is_non_drainable_name(item.model_alias):
            continue
        prio = _candidate_priority(item, alias_counts)
        if prio[0] < 99:
            candidates.append((prio, item))

    candidates.sort(key=lambda x: x[0])
    return [
        {
            "instance_id": c.instance_id,
            "pid": c.pid,
            "tenant_id": c.tenant_id,
            "model_alias": c.model_alias,
            "drainable": c.drainable,
            "critical": c.critical,
            "service_tier": c.service_tier,
            "restore_priority": c.restore_priority,
            "priority": p[0],
        }
        for p, c in candidates
    ]


def release_capacity(db: Session, target_free_vram_mib: int | None = None, safety_margin_mib: int | None = None, dry_run: bool = True, lease_id: str | None = None, tenant_id: str | None = None, request_id: str | None = None) -> dict:
    settings = get_settings()
    target = target_free_vram_mib if target_free_vram_mib is not None else settings.client_gpu0_target_free_vram_mib
    safety = safety_margin_mib if safety_margin_mib is not None else settings.client_gpu0_safety_margin_mib
    required = target + safety

    snapshot = create_snapshot(db, lease_id=lease_id, tenant_id=tenant_id, notes="pre-release snapshot", request_id=request_id)
    pre = _gpu0_status_payload()
    actions: list[dict] = []
    warnings: list[str] = []

    current_free = pre["memory_free_mib"]
    if current_free < required:
        candidates = select_drain_candidates(db)
        for candidate in candidates:
            if current_free >= required:
                break
            action = {"action": "stop_backend", "candidate": candidate, "dry_run": dry_run}
            if dry_run:
                action["result"] = "planned"
                actions.append(action)
                continue

            result = stop_backend(db, instance_id=candidate["instance_id"])
            action["result"] = result
            actions.append(action)
            _log_event(db, "stop_backend", bool(result.get("ok")), action, lease_id=lease_id, tenant_id=tenant_id)
            post_step = _gpu0_status_payload()
            current_free = post_step["memory_free_mib"]

    post = _gpu0_status_payload()
    freed = max(post["memory_free_mib"] - pre["memory_free_mib"], 0)
    reached = post["memory_free_mib"] >= required
    if not reached:
        warnings.append("Unable to reach target with safe managed candidates")

    result = {
        "snapshot_id": snapshot["snapshot_id"],
        "freed_vram_mib": freed,
        "target_reached": reached,
        "actions_taken": actions,
        "warnings": warnings,
        "status_before": pre,
        "status_after": post,
        "required_free_vram_mib": required,
        "dry_run": dry_run,
    }
    _log_event(db, "drain", reached, result, lease_id=lease_id, tenant_id=tenant_id)
    return result


def _get_snapshot(db: Session, snapshot_id: str | None, lease_id: str | None) -> GpuStateSnapshot | None:
    if snapshot_id:
        return db.scalar(select(GpuStateSnapshot).where(GpuStateSnapshot.snapshot_id == snapshot_id))
    if lease_id:
        return db.scalar(
            select(GpuStateSnapshot)
            .where(GpuStateSnapshot.lease_id == lease_id)
            .order_by(GpuStateSnapshot.created_at.desc())
        )
    return db.scalar(select(GpuStateSnapshot).order_by(GpuStateSnapshot.created_at.desc()))


def restore_state(db: Session, snapshot_id: str | None = None, lease_id: str | None = None, dry_run: bool = True, request_id: str | None = None) -> dict:
    snap = _get_snapshot(db, snapshot_id, lease_id)
    if not snap:
        return {"ok": False, "error": "snapshot not found"}

    payload = json.loads(snap.snapshot_json)
    items = [b for b in payload.get("backends_known", []) if b.get("status") == "running" and b.get("gpu_device") == "CUDA0"]
    items.sort(key=lambda x: (x.get("restore_priority", 100), x.get("created_at") or ""))

    restored: list[dict] = []
    skipped: list[dict] = []

    for item in items:
        already = db.scalar(
            select(BackendInstance).where(
                BackendInstance.status == "running",
                BackendInstance.model_alias == item.get("model_alias"),
                BackendInstance.tenant_id == item.get("tenant_id"),
                BackendInstance.gpu_device == "CUDA0",
            )
        )
        if already:
            skipped.append({"instance_id": item.get("instance_id"), "reason": "already_active", "active_instance_id": already.instance_id})
            continue

        if dry_run:
            restored.append({"instance_id": item.get("instance_id"), "planned": True, "model_alias": item.get("model_alias")})
            continue

        started = start_backend(
            db,
            model_alias=item.get("model_alias"),
            tenant_id=item.get("tenant_id"),
            gpu_preference="CUDA0",
            task_type=item.get("task_type") or "chat",
            host="127.0.0.1",
            port=item.get("port") or 9001,
            metadata={
                "drainable": bool(item.get("drainable", True)),
                "critical": bool(item.get("critical", False)),
                "service_tier": item.get("service_tier") or "standard",
                "restore_priority": int(item.get("restore_priority", 100)),
            },
        )
        restored.append({"instance_id": started.instance_id, "model_alias": started.model_alias, "status": started.status})

    result = {
        "ok": True,
        "snapshot_id": snap.snapshot_id,
        "lease_id": snap.lease_id,
        "dry_run": dry_run,
        "restored": restored,
        "skipped": skipped,
        "request_id": request_id,
    }
    _log_event(db, "restore", True, result, lease_id=snap.lease_id, tenant_id=snap.tenant_id)
    return result
