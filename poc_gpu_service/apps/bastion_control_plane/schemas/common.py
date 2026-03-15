from pydantic import BaseModel


class EnsureModelRequest(BaseModel):
    model_alias: str


class LeaseCreateRequest(BaseModel):
    model_alias: str
    task_type: str = "chat"
    requested_gpu: str | None = None


class LeaseCloseRequest(BaseModel):
    lease_id: str


class ChatRequest(BaseModel):
    lease_id: str
    messages: list[dict]
    temperature: float | None = 0.2


class EmbeddingsRequest(BaseModel):
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
