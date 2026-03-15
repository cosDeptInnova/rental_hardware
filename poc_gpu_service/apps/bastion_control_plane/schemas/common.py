from pydantic import BaseModel


class EnsureModelRequest(BaseModel):
    model_alias: str


class LeaseCreateRequest(BaseModel):
    model_alias: str
    task_type: str = "chat"
    requested_gpu: str | None = None


class ChatRequest(BaseModel):
    lease_id: str
    messages: list[dict]
    temperature: float | None = 0.2


class EmbeddingsRequest(BaseModel):
    lease_id: str
    input: str | list[str]
