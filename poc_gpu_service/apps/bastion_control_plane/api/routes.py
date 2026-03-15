from datetime import datetime
import uuid
import json

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from apps.bastion_control_plane.db.session import get_db
from apps.bastion_control_plane.models.db_models import ApiKey, Lease, RequestLog
from apps.bastion_control_plane.schemas.common import (
    EnsureModelRequest,
    LeaseCreateRequest,
    LeaseCloseRequest,
    ChatRequest,
    EmbeddingsRequest,
    GpuSnapshotRequest,
    GpuReleaseRequest,
    GpuRestoreRequest,
)
from apps.bastion_control_plane.services.auth import require_api_key
from apps.bastion_control_plane.services.capacity_manager import CapacityManager
from apps.bastion_control_plane.services.costing import estimate_cost
from apps.bastion_control_plane.services.gpu_agent_client import GpuAgentClient
from shared.config import get_settings
from shared.utils.catalog import CatalogService

router = APIRouter()
settings = get_settings()
cat = CatalogService(settings.catalog_path, settings.model_storage_root)
client = GpuAgentClient()
capacity_manager = CapacityManager()


@router.get("/health")
def health():
    return {"status": "ok", "service": "bastion-control-plane"}


@router.get("/v1/catalog")
def list_catalog(api_key: ApiKey = Depends(require_api_key)):
    return {"models": cat.list_enabled_for_tenant(api_key.tenant_id)}


@router.post("/v1/models/ensure")
async def ensure_model(payload: EnsureModelRequest, api_key: ApiKey = Depends(require_api_key)):
    ok, msg = cat.validate_deployable(payload.model_alias, api_key.tenant_id)
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    return await client.call("POST", "/internal/models/ensure", payload.model_dump())


@router.post("/v1/leases")
async def create_lease(payload: LeaseCreateRequest, db: Session = Depends(get_db), api_key: ApiKey = Depends(require_api_key)):
    ok, msg = cat.validate_deployable(payload.model_alias, api_key.tenant_id)
    if not ok:
        raise HTTPException(status_code=400, detail=msg)

    lease_id = f"lease-{uuid.uuid4().hex[:12]}"
    requested_gpu = payload.requested_gpu or settings.default_gpu_device_for_client

    handoff = None
    if requested_gpu == "CUDA0" and settings.enable_gpu0_handoff:
        handoff = await capacity_manager.on_lease_create(lease_id=lease_id, tenant_id=api_key.tenant_id, requested_gpu=requested_gpu)
        if not handoff.get("release", {}).get("target_reached", True):
            raise HTTPException(status_code=409, detail={"message": "Insufficient safe free capacity on GPU0", "handoff": handoff})

    backend = await client.call(
        "POST",
        "/internal/backends/start",
        {
            "model_alias": payload.model_alias,
            "tenant_id": api_key.tenant_id,
            "task_type": payload.task_type,
            "gpu_preference": requested_gpu,
        },
    )

    lease = Lease(
        lease_id=lease_id,
        tenant_id=api_key.tenant_id,
        model_alias=payload.model_alias,
        task_type=payload.task_type,
        requested_gpu=requested_gpu,
        assigned_backend_instance_id=backend["instance_id"],
        endpoint_path=f"/v1/{payload.task_type if payload.task_type!='chat' else 'chat/completions'}",
        status="active",
    )
    db.add(lease)
    db.commit()
    return {"lease_id": lease_id, "backend": backend, "status": "active", "handoff": handoff}


@router.post("/v1/leases/close")
async def close_lease(payload: LeaseCloseRequest, db: Session = Depends(get_db), api_key: ApiKey = Depends(require_api_key)):
    lease = db.scalar(select(Lease).where(Lease.lease_id == payload.lease_id, Lease.tenant_id == api_key.tenant_id))
    if not lease:
        raise HTTPException(status_code=404, detail="Lease not found")

    stop_result = await client.call("POST", "/internal/backends/stop", {"instance_id": lease.assigned_backend_instance_id})
    lease.status = "closed"
    lease.expires_at = datetime.utcnow()
    db.commit()
    restore = await capacity_manager.on_lease_close(lease.lease_id)
    return {"ok": True, "lease_id": lease.lease_id, "stop": stop_result, "restore": restore}


@router.get("/v1/leases")
def list_leases(db: Session = Depends(get_db), api_key: ApiKey = Depends(require_api_key)):
    data = db.scalars(select(Lease).where(Lease.tenant_id == api_key.tenant_id)).all()
    return {"items": [l.__dict__ for l in data]}


@router.get("/v1/leases/{lease_id}")
def get_lease(lease_id: str, db: Session = Depends(get_db), api_key: ApiKey = Depends(require_api_key)):
    lease = db.scalar(select(Lease).where(Lease.lease_id == lease_id, Lease.tenant_id == api_key.tenant_id))
    if not lease:
        raise HTTPException(status_code=404, detail="Lease not found")
    return lease.__dict__


async def _infer(path: str, lease_id: str, payload: dict, db: Session, api_key: ApiKey, request: Request):
    lease = db.scalar(select(Lease).where(Lease.lease_id == lease_id, Lease.tenant_id == api_key.tenant_id))
    if not lease:
        raise HTTPException(status_code=404, detail="Lease not found")
    started = datetime.utcnow()
    resp = await client.call("POST", path, {"lease_id": lease_id, **payload})
    finished = datetime.utcnow()
    latency = (finished - started).total_seconds()
    usage = resp.get("usage", {})
    cost = estimate_cost(usage.get("prompt_tokens"), usage.get("completion_tokens"), latency, len(json.dumps(resp).encode()))
    log = RequestLog(
        request_id=getattr(request.state, "request_id", ""),
        tenant_id=api_key.tenant_id,
        api_key_id=api_key.id,
        endpoint=request.url.path,
        model_alias=lease.model_alias,
        task_type=lease.task_type,
        backend_instance_id=lease.assigned_backend_instance_id,
        started_at=started,
        finished_at=finished,
        latency_ms=latency * 1000,
        http_status=200,
        request_bytes=len(json.dumps(payload).encode()),
        response_bytes=len(json.dumps(resp).encode()),
        prompt_tokens=usage.get("prompt_tokens"),
        completion_tokens=usage.get("completion_tokens"),
        total_tokens=usage.get("total_tokens"),
        gpu_energy_est_wh=cost["gpu_energy_est_wh"],
        notes_json=json.dumps(cost),
    )
    db.add(log)
    db.commit()
    resp["costing"] = cost
    return resp


@router.post("/v1/chat/completions")
async def chat(payload: ChatRequest, request: Request, db: Session = Depends(get_db), api_key: ApiKey = Depends(require_api_key)):
    return await _infer("/internal/infer/chat", payload.lease_id, payload.model_dump(exclude={"lease_id"}), db, api_key, request)


@router.post("/v1/embeddings")
async def embeddings(payload: EmbeddingsRequest, request: Request, db: Session = Depends(get_db), api_key: ApiKey = Depends(require_api_key)):
    return await _infer("/internal/infer/embeddings", payload.lease_id, payload.model_dump(exclude={"lease_id"}), db, api_key, request)


@router.get("/v1/usage/summary")
def usage_summary(db: Session = Depends(get_db), api_key: ApiKey = Depends(require_api_key)):
    count = db.scalar(select(func.count(RequestLog.id)).where(RequestLog.tenant_id == api_key.tenant_id))
    total_bytes = db.scalar(select(func.coalesce(func.sum(RequestLog.response_bytes), 0)).where(RequestLog.tenant_id == api_key.tenant_id))
    return {"tenant_id": api_key.tenant_id, "requests": count or 0, "response_bytes": total_bytes or 0}


@router.get("/v1/usage/requests")
def usage_requests(db: Session = Depends(get_db), api_key: ApiKey = Depends(require_api_key)):
    logs = db.scalars(select(RequestLog).where(RequestLog.tenant_id == api_key.tenant_id).order_by(RequestLog.id.desc()).limit(100)).all()
    return {"items": [l.__dict__ for l in logs]}


@router.get("/v1/audit/requests/{request_id}")
def audit_request(request_id: str, db: Session = Depends(get_db), api_key: ApiKey = Depends(require_api_key)):
    log = db.scalar(select(RequestLog).where(RequestLog.request_id == request_id, RequestLog.tenant_id == api_key.tenant_id))
    if not log:
        raise HTTPException(status_code=404, detail="request_id not found")
    return log.__dict__


@router.post("/v1/admin/gpu0/snapshot")
async def admin_snapshot(payload: GpuSnapshotRequest, api_key: ApiKey = Depends(require_api_key)):
    return await client.call("POST", "/internal/gpu/0/snapshot", payload.model_dump())


@router.post("/v1/admin/gpu0/release")
async def admin_release(payload: GpuReleaseRequest, api_key: ApiKey = Depends(require_api_key)):
    return await client.call("POST", "/internal/gpu/0/release", payload.model_dump())


@router.post("/v1/admin/gpu0/restore")
async def admin_restore(payload: GpuRestoreRequest, api_key: ApiKey = Depends(require_api_key)):
    return await client.call("POST", "/internal/gpu/0/restore", payload.model_dump())


@router.get("/v1/admin/gpu0/status")
async def admin_status(api_key: ApiKey = Depends(require_api_key)):
    return await client.call("GET", "/internal/gpu/0/status")


@router.get("/v1/admin/gpu0/snapshots")
async def admin_snapshots(api_key: ApiKey = Depends(require_api_key)):
    return await client.call("GET", "/internal/gpu/0/snapshots")


@router.get("/v1/admin/gpu0/handoff-events")
async def admin_handoff_events(api_key: ApiKey = Depends(require_api_key)):
    return await client.call("GET", "/internal/gpu/0/handoff-events")


@router.get("/v1/demo/status")
async def demo_status(db: Session = Depends(get_db), api_key: ApiKey = Depends(require_api_key)):
    status = await client.call("GET", "/internal/gpu/0/status")
    leases = db.scalars(select(Lease).where(Lease.status == "active").order_by(Lease.created_at.desc())).all()
    snapshots_resp = await client.call("GET", "/internal/gpu/0/snapshots")
    events_resp = await client.call("GET", "/internal/gpu/0/handoff-events")
    snapshots = snapshots_resp.get("items", [])
    events = events_resp.get("items", [])
    release_actions = [e for e in events if e.get("action_type") in {"drain", "stop_backend", "warn"}][:10]
    restore_actions = [e for e in events if e.get("action_type") in {"restore", "start_backend"}][:10]
    gpu_status = status.get("status", {})
    return {
        "gpu0": {
            "free_mib": gpu_status.get("memory_free_mib"),
            "used_mib": gpu_status.get("memory_used_mib"),
            "reserved_target_mib": gpu_status.get("required_free_vram_mib"),
            "target_satisfiable": gpu_status.get("target_satisfiable"),
        },
        "active_leases": [l.__dict__ for l in leases],
        "last_snapshot": snapshots[0] if snapshots else None,
        "last_release_actions": release_actions,
        "last_restore_actions": restore_actions,
    }
