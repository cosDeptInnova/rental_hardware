from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field, model_validator


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
    input_tokens: int
    output_tokens: int
    created_at: datetime
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    worker_state: str
    exit_code: Optional[int] = None
    execution_error: Optional[str] = None
    avg_gpu_util: float
    avg_power_watts: float
    peak_power_watts: float
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
    total_input_tokens: int
    total_output_tokens: int
    total_energy_joules: float
    gpu_cost: float
    token_cost: float
    energy_cost: float
    estimated_cost: float
    currency: str = "EUR"


class PlanLimits(BaseModel):
    requests_per_minute: int = Field(ge=1, le=5_000)
    max_concurrent_jobs: int = Field(ge=1, le=128)
    max_job_seconds: int = Field(ge=1, le=86_400)
    max_input_bytes: int = Field(ge=1, le=1_000_000_000)
    monthly_credit_limit: float = Field(gt=0, le=10_000_000)
    price_per_gpu_second: float = Field(gt=0, le=100)
    gpu_share: float = Field(gt=0, le=1)
    max_power_watts: float = Field(gt=0, le=10_000)
    max_energy_joules: float = Field(gt=0, le=1_000_000_000)
    max_output_tokens: int = Field(ge=1, le=10_000_000)

    @model_validator(mode="after")
    def validate_ratio(self):
        if self.max_energy_joules < self.max_power_watts:
            raise ValueError("max_energy_joules must be >= max_power_watts")
        return self


class PlanCreate(PlanLimits):
    plan_name: str = Field(min_length=3, max_length=120)


class PlanUpdate(BaseModel):
    requests_per_minute: Optional[int] = Field(default=None, ge=1, le=5_000)
    max_concurrent_jobs: Optional[int] = Field(default=None, ge=1, le=128)
    max_job_seconds: Optional[int] = Field(default=None, ge=1, le=86_400)
    max_input_bytes: Optional[int] = Field(default=None, ge=1, le=1_000_000_000)
    monthly_credit_limit: Optional[float] = Field(default=None, gt=0, le=10_000_000)
    price_per_gpu_second: Optional[float] = Field(default=None, gt=0, le=100)
    gpu_share: Optional[float] = Field(default=None, gt=0, le=1)
    max_power_watts: Optional[float] = Field(default=None, gt=0, le=10_000)
    max_energy_joules: Optional[float] = Field(default=None, gt=0, le=1_000_000_000)
    max_output_tokens: Optional[int] = Field(default=None, ge=1, le=10_000_000)
    is_active: Optional[bool] = None


class PlanPublic(PlanCreate):
    is_active: bool
    created_at: datetime
    updated_at: Optional[datetime] = None


class ClientCreate(BaseModel):
    client_name: str = Field(min_length=3, max_length=120)
    api_key: str = Field(min_length=16, max_length=256)
    scopes: list[str] = Field(min_length=1)
    plan_name: Optional[str] = Field(default=None, min_length=3, max_length=120)
    requests_per_minute: int = Field(ge=1, le=5_000)
    max_concurrent_jobs: int = Field(ge=1, le=128)
    max_job_seconds: int = Field(ge=1, le=86_400)
    max_input_bytes: int = Field(ge=1, le=1_000_000_000)
    monthly_credit_limit: float = Field(gt=0, le=10_000_000)
    price_per_gpu_second: float = Field(gt=0, le=100)
    gpu_share: float = Field(gt=0, le=1)
    max_tokens_per_job: int = Field(ge=1, le=10_000_000)
    monthly_token_limit: int = Field(ge=1, le=100_000_000)
    max_power_watts: float = Field(gt=0, le=10_000)
    max_energy_joules_per_job: float = Field(gt=0, le=1_000_000_000)
    is_admin: bool = False


class ClientUpdate(BaseModel):
    api_key: Optional[str] = Field(default=None, min_length=16, max_length=256)
    scopes: Optional[list[str]] = None
    plan_name: Optional[str] = Field(default=None, min_length=3, max_length=120)
    requests_per_minute: Optional[int] = Field(default=None, ge=1, le=5_000)
    max_concurrent_jobs: Optional[int] = Field(default=None, ge=1, le=128)
    max_job_seconds: Optional[int] = Field(default=None, ge=1, le=86_400)
    max_input_bytes: Optional[int] = Field(default=None, ge=1, le=1_000_000_000)
    monthly_credit_limit: Optional[float] = Field(default=None, gt=0, le=10_000_000)
    price_per_gpu_second: Optional[float] = Field(default=None, gt=0, le=100)
    gpu_share: Optional[float] = Field(default=None, gt=0, le=1)
    max_tokens_per_job: Optional[int] = Field(default=None, ge=1, le=10_000_000)
    monthly_token_limit: Optional[int] = Field(default=None, ge=1, le=100_000_000)
    max_power_watts: Optional[float] = Field(default=None, gt=0, le=10_000)
    max_energy_joules_per_job: Optional[float] = Field(default=None, gt=0, le=1_000_000_000)
    is_admin: Optional[bool] = None
    is_active: Optional[bool] = None


class ClientPublic(BaseModel):
    client_name: str
    scopes: list[str]
    plan_name: str
    requests_per_minute: int
    max_concurrent_jobs: int
    max_job_seconds: int
    max_input_bytes: int
    monthly_credit_limit: float
    price_per_gpu_second: float
    gpu_share: float
    max_tokens_per_job: int
    monthly_token_limit: int
    max_power_watts: float
    max_energy_joules_per_job: float
    is_admin: bool
    is_active: bool
    created_at: datetime
    updated_at: Optional[datetime] = None
