import json
from datetime import datetime

from sqlalchemy import select, text

from apps.bastion_control_plane.db.session import engine, SessionLocal
from apps.bastion_control_plane.models.db_models import Base, Tenant, ApiKey, BackendInstance


def _table_columns(db, table_name: str) -> set[str]:
    rows = db.execute(text(f"PRAGMA table_info({table_name})")).fetchall()
    return {str(r[1]) for r in rows}


def _add_column_if_missing(db, table_name: str, column_name: str, ddl_type: str) -> None:
    if column_name not in _table_columns(db, table_name):
        db.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {ddl_type}"))


def _apply_sqlite_hardening_migrations(db) -> None:
    _add_column_if_missing(db, "backend_instances", "started_at", "DATETIME")
    _add_column_if_missing(db, "backend_instances", "stopped_at", "DATETIME")
    _add_column_if_missing(db, "backend_instances", "last_healthcheck_at", "DATETIME")
    _add_column_if_missing(db, "backend_instances", "extra_json", "TEXT")
    _add_column_if_missing(db, "backend_instances", "drainable", "BOOLEAN DEFAULT 1")
    _add_column_if_missing(db, "backend_instances", "critical", "BOOLEAN DEFAULT 0")
    _add_column_if_missing(db, "backend_instances", "service_tier", "VARCHAR(50) DEFAULT 'standard'")
    _add_column_if_missing(db, "backend_instances", "preferred_gpu", "VARCHAR(50)")
    _add_column_if_missing(db, "backend_instances", "restore_priority", "INTEGER DEFAULT 100")


def _seed_demo_backends(db) -> None:
    base_command = json.dumps({"command": ["llama-server", "--demo-seed"]})
    if not db.scalar(select(BackendInstance).where(BackendInstance.instance_id == "seed-internal-drainable-gpu0")):
        db.add(
            BackendInstance(
                instance_id="seed-internal-drainable-gpu0",
                tenant_id="interno",
                model_alias="mistral-7b-instruct",
                task_type="chat",
                engine="llama_cpp",
                gpu_device="CUDA0",
                host="127.0.0.1",
                port=9101,
                pid=None,
                status="running",
                created_at=datetime.utcnow(),
                started_at=datetime.utcnow(),
                extra_json=base_command,
                drainable=True,
                critical=False,
                service_tier="production_replicas",
                preferred_gpu="CUDA0",
                restore_priority=20,
            )
        )

    if not db.scalar(select(BackendInstance).where(BackendInstance.instance_id == "seed-internal-critical-gpu0")):
        db.add(
            BackendInstance(
                instance_id="seed-internal-critical-gpu0",
                tenant_id="interno",
                model_alias="llama3-8b-instruct",
                task_type="chat",
                engine="llama_cpp",
                gpu_device="CUDA0",
                host="127.0.0.1",
                port=9102,
                pid=None,
                status="running",
                created_at=datetime.utcnow(),
                started_at=datetime.utcnow(),
                extra_json=base_command,
                drainable=False,
                critical=True,
                service_tier="core",
                preferred_gpu="CUDA0",
                restore_priority=5,
            )
        )


def init_db_and_seed() -> None:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        _apply_sqlite_hardening_migrations(db)
        if not db.scalar(select(Tenant).where(Tenant.tenant_id == "interno")):
            db.add(Tenant(tenant_id="interno", name="Tenant interno"))
        if not db.scalar(select(Tenant).where(Tenant.tenant_id == "cliente1")):
            db.add(Tenant(tenant_id="cliente1", name="Cliente 1"))
        if not db.scalar(select(ApiKey).where(ApiKey.key == "internal_key_456")):
            db.add(ApiKey(key="internal_key_456", tenant_id="interno"))
        if not db.scalar(select(ApiKey).where(ApiKey.key == "client1_key_123")):
            db.add(ApiKey(key="client1_key_123", tenant_id="cliente1"))
        _seed_demo_backends(db)
        db.commit()
    finally:
        db.close()
