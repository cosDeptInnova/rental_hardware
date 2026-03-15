from datetime import datetime
from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


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
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    stopped_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_healthcheck_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    extra_json: Mapped[str | None] = mapped_column(Text, nullable=True)


class GpuSample(Base):
    __tablename__ = "gpu_samples"
    id: Mapped[int] = mapped_column(primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    payload_json: Mapped[str] = mapped_column(Text)


class ProcessSample(Base):
    __tablename__ = "process_samples"
    id: Mapped[int] = mapped_column(primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    payload_json: Mapped[str] = mapped_column(Text)
