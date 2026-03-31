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


class TenantCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class TenantCreateRead(BaseModel):
    tenant_id: str
    name: str
    api_key: str


class JobCreate(BaseModel):
    service_type: ServiceType
    requested_vram_mb: int = Field(gt=0)
    priority: int = Field(ge=0, le=100, default=50)
    payload: dict[str, Any] = Field(default_factory=dict)
    model: str = Field(default="default-model")


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


class InferenceRequest(BaseModel):
    model: str
    requested_vram_mb: int = Field(gt=0)
    priority: int = Field(ge=0, le=100, default=50)
    payload: dict[str, Any] = Field(default_factory=dict)


class EmbeddingsRequest(BaseModel):
    model: str
    requested_vram_mb: int = Field(gt=0)
    priority: int = Field(ge=0, le=100, default=50)
    payload: dict[str, Any] = Field(default_factory=dict)


class ServiceResponse(BaseModel):
    request_id: str
    job_id: str
    state: JobState
    status_code: int
    service_type: ServiceType
    model: str
    result: dict[str, Any]


class AnalyticsServiceBreakdown(BaseModel):
    service_type: ServiceType
    requests: int
    request_tokens: int
    response_tokens: int
    total_tokens: int
    avg_latency_ms: float


class AnalyticsSummaryRead(BaseModel):
    requests_total: int
    success_total: int
    failed_total: int
    queued_total: int
    running_total: int
    finished_total: int
    failed_jobs_total: int
    request_tokens_total: int
    response_tokens_total: int
    total_tokens_total: int
    avg_latency_ms: float
    by_service: list[AnalyticsServiceBreakdown]
    by_state: dict[str, int] = Field(default_factory=dict)


class QuotaConfig(BaseModel):
    requests_per_day: int = Field(ge=0, default=0)
    requests_per_month: int = Field(ge=0, default=0)
    tokens_per_day: int = Field(ge=0, default=0)
    tokens_per_month: int = Field(ge=0, default=0)


class SessionStateRead(BaseModel):
    tenant_id: str
    revoked: bool
