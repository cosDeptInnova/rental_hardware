from pydantic import BaseModel, Field
from typing import Optional, Literal
from datetime import datetime

class JobCreate(BaseModel):
    workload_name: str = Field(min_length=3, max_length=100)
    estimated_seconds: int = Field(ge=1, le=3600)
    input_bytes: int = Field(ge=0, le=50_000_000)
    gpu_share: float = Field(default=1.0, ge=0.1, le=1.0)
    idempotency_key: str = Field(min_length=8, max_length=128)

class JobPublic(BaseModel):
    id: str
    client_name: str
    workload_name: str
    status: Literal["queued", "running", "succeeded", "failed"]
    estimated_seconds: int
    billed_seconds: int
    gpu_seconds: float
    peak_vram_mb: int
    input_bytes: int
    output_bytes: int
    created_at: datetime
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    worker_state: str
    exit_code: Optional[int] = None
    execution_error: Optional[str] = None
    avg_gpu_util: float
    avg_power_watts: float
    energy_joules: float

class UsagePublic(BaseModel):
    client_name: str
    month: str
    total_requests: int
    total_input_bytes: int
    total_output_bytes: int
    total_billed_seconds: int
    total_gpu_seconds: float
    total_peak_vram_mb: int
    estimated_cost: float
    currency: str = "EUR"
