from functools import lru_cache
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "dev"
    app_name: str = "gpu-poc"
    service_name: str = "service"
    log_level: str = "INFO"
    bastion_api_keys: str = ""
    internal_agent_token: str = ""
    database_url: str = "sqlite:///./state/poc_gpu.db"
    gpu_agent_base_url: str = "http://127.0.0.1:8101"
    gpu_agent_timeout_seconds: int = 30
    catalog_path: str = "./catalog/models.json"
    model_storage_root: str = "./state/models"
    llama_server_path: str = "C:/llama/llama-server.exe"
    default_gpu_device_for_client: str = "CUDA0"
    default_gpu_device_for_internal: str = "CUDA1"
    default_host: str = "127.0.0.1"
    base_public_url: str = "http://127.0.0.1:8000"
    rate_limit_per_minute: int = Field(default=120, ge=1)
    cost_fixed_per_request: float = 0.0005
    cost_per_1k_input_tokens: float = 0.001
    cost_per_1k_output_tokens: float = 0.002
    cost_per_second_backend: float = 0.0003
    cost_per_gb_network_egress: float = 0.05
    cost_per_kwh_gpu: float = 0.25

    @property
    def parsed_api_keys(self) -> list[str]:
        return [k.strip() for k in self.bastion_api_keys.split(",") if k.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
