from datetime import datetime
from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Tenant(Base):
    __tablename__ = "tenants"
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200))
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class ApiKey(Base):
    __tablename__ = "api_keys"
    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    tenant_id: Mapped[str] = mapped_column(String(100), index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class BackendInstance(Base):
    __tablename__ = "backend_instances"
    instance_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(100), index=True)
    model_alias: Mapped[str] = mapped_column(String(200), index=True)
    task_type: Mapped[str] = mapped_column(String(50))
    engine: Mapped[str] = mapped_column(String(50))
    gpu_device: Mapped[str] = mapped_column(String(50))
    host: Mapped[str] = mapped_column(String(100))
    port: Mapped[int] = mapped_column(Integer)
    pid: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="starting")

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    drainable: Mapped[bool] = mapped_column(Boolean, default=True)
    critical: Mapped[bool] = mapped_column(Boolean, default=False)
    service_tier: Mapped[str] = mapped_column(String(50), default="standard")
    preferred_gpu: Mapped[str | None] = mapped_column(String(50), nullable=True)
    restore_priority: Mapped[int] = mapped_column(Integer, default=100)


class Lease(Base):
    __tablename__ = "leases"
    lease_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(100), index=True)
    model_alias: Mapped[str] = mapped_column(String(200))
    task_type: Mapped[str] = mapped_column(String(50))
    requested_gpu: Mapped[str] = mapped_column(String(50))
    assigned_backend_instance_id: Mapped[str] = mapped_column(String(100))
    endpoint_path: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(50), default="active")

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class RequestLog(Base):
    __tablename__ = "request_logs"
    id: Mapped[int] = mapped_column(primary_key=True)
    request_id: Mapped[str] = mapped_column(String(100), index=True)
    tenant_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    api_key_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    endpoint: Mapped[str] = mapped_column(String(255))
    model_alias: Mapped[str | None] = mapped_column(String(200), nullable=True)
    task_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    backend_instance_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    latency_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    http_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    request_bytes: Mapped[int] = mapped_column(Integer, default=0)
    response_bytes: Mapped[int] = mapped_column(Integer, default=0)
    prompt_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    completion_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    gpu_energy_est_wh: Mapped[float | None] = mapped_column(Float, nullable=True)
    cpu_user_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    cpu_system_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    ram_rss_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    notes_json: Mapped[str | None] = mapped_column(Text, nullable=True)


class GpuStateSnapshot(Base):
    __tablename__ = "gpu_state_snapshots"
    snapshot_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    lease_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    tenant_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    gpu_index: Mapped[int] = mapped_column(Integer)
    snapshot_json: Mapped[str] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class HandoffEvent(Base):
    __tablename__ = "handoff_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    lease_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    tenant_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    action_type: Mapped[str] = mapped_column(String(50), index=True)
    success: Mapped[bool] = mapped_column(Boolean, default=True)
    details_json: Mapped[str] = mapped_column(Text)
