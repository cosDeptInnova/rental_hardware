from datetime import datetime
import json
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from shared.config import get_settings
from shared.utils.catalog import CatalogService
from apps.bastion_control_plane.db.session import get_db
from apps.bastion_control_plane.models.db_models import ApiKey, Lease, RequestLog
from apps.bastion_control_plane.schemas.common import EnsureModelRequest, LeaseCreateRequest, ChatRequest, EmbeddingsRequest
from apps.bastion_control_plane.services.auth import require_api_key
from apps.bastion_control_plane.services.costing import estimate_cost
from apps.bastion_control_plane.services.gpu_agent_client import GpuAgentClient

router = APIRouter()
settings = get_settings()
cat = CatalogService(settings.catalog_path, settings.model_storage_root)
client = GpuAgentClient()


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
    backend = await client.call("POST", "/internal/backends/start", {
        "model_alias": payload.model_alias,
        "tenant_id": api_key.tenant_id,
        "task_type": payload.task_type,
        "gpu_preference": payload.requested_gpu or settings.default_gpu_device_for_client,
    })
    lease_id = f"lease-{datetime.utcnow().timestamp():.0f}"
    lease = Lease(
        lease_id=lease_id,
        tenant_id=api_key.tenant_id,
        model_alias=payload.model_alias,
        task_type=payload.task_type,
        requested_gpu=payload.requested_gpu or settings.default_gpu_device_for_client,
        assigned_backend_instance_id=backend["instance_id"],
        endpoint_path=f"/v1/{payload.task_type if payload.task_type!='chat' else 'chat/completions'}",
        status="active",
    )
    db.add(lease)
    db.commit()
    return {"lease_id": lease_id, "backend": backend, "status": "active"}


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
