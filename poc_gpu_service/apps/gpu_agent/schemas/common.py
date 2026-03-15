from pydantic import BaseModel, Field


class EnsureModelRequest(BaseModel):
    model_alias: str


class StartBackendRequest(BaseModel):
    model_alias: str
    tenant_id: str
    task_type: str = "chat"
    gpu_preference: str = "CUDA0"
    host: str = "127.0.0.1"
    port: int = Field(default=9001, ge=1024, le=65535)
    ctx_size: int = 4096
    parallel: int = 2


class StopBackendRequest(BaseModel):
    instance_id: str | None = None
    pid: int | None = None


class ChatInferRequest(BaseModel):
    lease_id: str
    messages: list[dict]
    temperature: float | None = 0.2


class EmbeddingsInferRequest(BaseModel):
    lease_id: str
    input: str | list[str]


class GpuSnapshotRequest(BaseModel):
    lease_id: str | None = None
    tenant_id: str | None = None
    notes: str | None = None


class GpuReleaseRequest(BaseModel):
    lease_id: str | None = None
    tenant_id: str | None = None
    target_free_vram_mib: int | None = None
    safety_margin_mib: int | None = None
    dry_run: bool = True


class GpuRestoreRequest(BaseModel):
    snapshot_id: str | None = None
    lease_id: str | None = None
    dry_run: bool = True
