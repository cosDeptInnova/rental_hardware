import json
import subprocess
import uuid
from datetime import datetime
from pathlib import Path
from sqlalchemy import select
from sqlalchemy.orm import Session
from shared.config import get_settings
from shared.utils.catalog import CatalogService
from apps.gpu_agent.models.db_models import BackendInstance
from apps.gpu_agent.services.command_builder import build_llama_command


def start_backend(db: Session, model_alias: str, tenant_id: str, gpu_preference: str, task_type: str, host: str = "127.0.0.1", port: int = 9001, ctx_size: int = 4096, parallel: int = 2):
    s = get_settings()
    catalog = CatalogService(s.catalog_path, s.model_storage_root)
    model = catalog.get_by_alias(model_alias)
    if not model:
        raise ValueError("model not found")
    model_path = Path(s.model_storage_root) / model["local_path"]
    if model["engine"] == "llama_cpp":
        cmd = build_llama_command(s.llama_server_path, str(model_path), host, port, gpu_preference, ctx_size, parallel)
        proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        pid = proc.pid
    else:
        pid = None
    instance_id = str(uuid.uuid4())
    instance = BackendInstance(
        instance_id=instance_id,
        tenant_id=tenant_id,
        model_alias=model_alias,
        task_type=task_type,
        engine=model["engine"],
        gpu_device=gpu_preference,
        host=host,
        port=port,
        pid=pid,
        status="running",
        started_at=datetime.utcnow(),
        extra_json=json.dumps({"command": cmd if model["engine"] == "llama_cpp" else []}),
    )
    db.add(instance)
    db.commit()
    Path("state").mkdir(exist_ok=True)
    Path(f"state/{instance_id}.json").write_text(json.dumps({"instance_id": instance_id, "pid": pid}), encoding="utf-8")
    return instance


def stop_backend(db: Session, instance_id: str | None = None, pid: int | None = None):
    instance = None
    if instance_id:
        instance = db.scalar(select(BackendInstance).where(BackendInstance.instance_id == instance_id))
    elif pid:
        instance = db.scalar(select(BackendInstance).where(BackendInstance.pid == pid))
    if not instance:
        return {"ok": False, "error": "backend not found"}
    if instance.pid:
        subprocess.run(["taskkill", "/PID", str(instance.pid), "/F"], capture_output=True, text=True)
    instance.status = "stopped"
    instance.stopped_at = datetime.utcnow()
    db.commit()
    return {"ok": True, "instance_id": instance.instance_id, "status": "stopped"}
