import json
from datetime import datetime

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from apps.gpu_agent.db.session import get_db
from apps.gpu_agent.models.db_models import BackendInstance, GpuSample, ProcessSample, GpuStateSnapshot, HandoffEvent
from apps.gpu_agent.schemas.common import (
    EnsureModelRequest,
    StartBackendRequest,
    StopBackendRequest,
    ChatInferRequest,
    EmbeddingsInferRequest,
    GpuSnapshotRequest,
    GpuReleaseRequest,
    GpuRestoreRequest,
)
from apps.gpu_agent.services.auth import require_internal_token
from apps.gpu_agent.services.backend_service import start_backend, stop_backend
from apps.gpu_agent.services.capacity_handoff_service import create_snapshot, release_capacity, restore_state, _gpu0_status_payload
from apps.gpu_agent.services.metrics_service import collect_gpu_metrics
from apps.gpu_agent.services.model_service import ensure_model
from shared.config import get_settings
from shared.utils.catalog import CatalogService

router = APIRouter(dependencies=[Depends(require_internal_token)])
settings = get_settings()
catalog = CatalogService(settings.catalog_path, settings.model_storage_root)


@router.get("/health")
def health():
    return {"status": "ok", "service": "gpu-agent"}


@router.get("/internal/models/inventory")
def inventory():
    items = []
    for model in catalog.load():
        items.append({"model_alias": model["model_alias"], "local_exists": (catalog.model_storage_root / model["local_path"]).exists()})
    return {"items": items}


@router.post("/internal/models/ensure")
def ensure(payload: EnsureModelRequest):
    result = ensure_model(payload.model_alias)
    if not result["ok"]:
        raise HTTPException(status_code=400, detail=result)
    return result


@router.get("/internal/backends")
def list_backends(db: Session = Depends(get_db)):
    items = db.scalars(select(BackendInstance).order_by(BackendInstance.created_at.desc())).all()
    return {"items": [i.__dict__ for i in items]}


@router.post("/internal/backends/start")
def start(payload: StartBackendRequest, db: Session = Depends(get_db)):
    ensure_model(payload.model_alias)
    instance = start_backend(db, payload.model_alias, payload.tenant_id, payload.gpu_preference, payload.task_type, payload.host, payload.port, payload.ctx_size, payload.parallel)
    return {"instance_id": instance.instance_id, "pid": instance.pid, "host": instance.host, "port": instance.port, "status": instance.status}


@router.post("/internal/backends/stop")
def stop(payload: StopBackendRequest, db: Session = Depends(get_db)):
    return stop_backend(db, payload.instance_id, payload.pid)


@router.get("/internal/backends/{instance_id}")
def get_backend(instance_id: str, db: Session = Depends(get_db)):
    item = db.scalar(select(BackendInstance).where(BackendInstance.instance_id == instance_id))
    if not item:
        raise HTTPException(status_code=404, detail="Not found")
    return item.__dict__


@router.get("/internal/metrics/gpu")
def gpu_metrics(db: Session = Depends(get_db)):
    data = collect_gpu_metrics()
    db.add(GpuSample(timestamp=datetime.utcnow(), payload_json=json.dumps(data)))
    db.commit()
    return data


@router.get("/internal/metrics/processes")
def process_metrics(db: Session = Depends(get_db)):
    data = collect_gpu_metrics().get("compute_apps", [])
    db.add(ProcessSample(timestamp=datetime.utcnow(), payload_json=json.dumps(data)))
    db.commit()
    return {"timestamp": datetime.utcnow().isoformat(), "processes": data}


@router.get("/internal/gpu/0/status")
def gpu0_status(db: Session = Depends(get_db)):
    latest = db.scalar(select(GpuStateSnapshot).order_by(GpuStateSnapshot.created_at.desc()))
    return {
        "status": _gpu0_status_payload(),
        "latest_snapshot": latest.__dict__ if latest else None,
    }


@router.post("/internal/gpu/0/snapshot")
def gpu0_snapshot(payload: GpuSnapshotRequest, request: Request, db: Session = Depends(get_db)):
    return create_snapshot(db, lease_id=payload.lease_id, tenant_id=payload.tenant_id, notes=payload.notes, request_id=getattr(request.state, "request_id", None))


@router.post("/internal/gpu/0/release")
def gpu0_release(payload: GpuReleaseRequest, request: Request, db: Session = Depends(get_db)):
    result = release_capacity(
        db,
        target_free_vram_mib=payload.target_free_vram_mib,
        safety_margin_mib=payload.safety_margin_mib,
        dry_run=payload.dry_run,
        lease_id=payload.lease_id,
        tenant_id=payload.tenant_id,
        request_id=getattr(request.state, "request_id", None),
    )
    if not payload.dry_run and not result.get("target_reached"):
        raise HTTPException(status_code=409, detail=result)
    return result


@router.post("/internal/gpu/0/restore")
def gpu0_restore(payload: GpuRestoreRequest, request: Request, db: Session = Depends(get_db)):
    return restore_state(db, snapshot_id=payload.snapshot_id, lease_id=payload.lease_id, dry_run=payload.dry_run, request_id=getattr(request.state, "request_id", None))


@router.get("/internal/gpu/0/snapshots")
def gpu0_snapshots(db: Session = Depends(get_db)):
    rows = db.scalars(select(GpuStateSnapshot).order_by(GpuStateSnapshot.created_at.desc()).limit(100)).all()
    return {"items": [r.__dict__ for r in rows]}


@router.get("/internal/gpu/0/handoff-events")
def gpu0_handoff_events(db: Session = Depends(get_db)):
    rows = db.scalars(select(HandoffEvent).order_by(HandoffEvent.id.desc()).limit(200)).all()
    return {"items": [r.__dict__ for r in rows]}


@router.post("/internal/infer/chat")
async def infer_chat(payload: ChatInferRequest, db: Session = Depends(get_db)):
    backend = db.scalar(select(BackendInstance).where(BackendInstance.status == "running").order_by(BackendInstance.created_at.desc()))
    if not backend:
        raise HTTPException(status_code=404, detail="No running backend")
    url = f"http://{backend.host}:{backend.port}/v1/chat/completions"
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            r = await client.post(url, json={"messages": payload.messages, "temperature": payload.temperature})
            if r.status_code < 400:
                return r.json()
    except Exception:
        pass
    text = "PoC stub response"
    return {"id": "chatcmpl-poc", "choices": [{"message": {"role": "assistant", "content": text}}], "usage": {"prompt_tokens": None, "completion_tokens": None, "total_tokens": None}}


@router.post("/internal/infer/embeddings")
def infer_embeddings(payload: EmbeddingsInferRequest):
    inputs = payload.input if isinstance(payload.input, list) else [payload.input]
    return {"data": [{"index": i, "embedding": [0.1, 0.2, 0.3]} for i, _ in enumerate(inputs)], "usage": {"prompt_tokens": None, "total_tokens": None}}
