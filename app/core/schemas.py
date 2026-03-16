from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ServiceType(str, Enum):
    INFERENCE = "inference"
    EMBEDDINGS = "embeddings"
    RAG = "rag"


class JobState(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    FINISHED = "finished"
    FAILED = "failed"
    REJECTED = "rejected"


class WorkerStatus(str, Enum):
    IDLE = "idle"
    BUSY = "busy"
    STOPPING = "stopping"
    STOPPED = "stopped"


class ReservationCreate(BaseModel):
    tenant_id: str
    reserved_vram_mb: int = Field(gt=0)
    max_concurrency: int = Field(gt=0)
    priority: int = Field(ge=0, le=100)
    allowed_services: list[ServiceType]
    preemptive: bool = True
    enabled: bool = True


class ReservationRead(ReservationCreate):
    id: str
    model_config = ConfigDict(from_attributes=True)


class JobCreate(BaseModel):
    service_type: ServiceType
    requested_vram_mb: int = Field(gt=0)
    priority: int = Field(ge=0, le=100, default=50)
    payload: dict[str, Any] = Field(default_factory=dict)


class JobRead(BaseModel):
    id: str
    external_id: str
    tenant_id: str
    service_type: ServiceType
    requested_vram_mb: int
    priority: int
    state: JobState
    worker_id: str | None = None
    error: str | None = None
    model_config = ConfigDict(from_attributes=True)


class JobDecision(BaseModel):
    admitted: bool
    reason: str
    gpu_index: int | None = None
    reclaimed_workers: list[str] = Field(default_factory=list)


class CapacityRead(BaseModel):
    index: int
    name: str
    uuid: str
    total_mb: int
    used_mb: int
    free_mb: int
    gpu_util: int
