from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    app_name: str = os.getenv("APP_NAME", "gpu-broker")
    environment: str = os.getenv("ENVIRONMENT", "dev")
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./gpu_broker.db")
    admin_token: str = os.getenv("ADMIN_TOKEN", "change-me")
    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    host: str = os.getenv("HOST", "0.0.0.0")
    port: int = int(os.getenv("PORT", "8000"))
    llama_server_url: str = os.getenv("LLAMA_SERVER_URL", "")
    redis_url: str = os.getenv("REDIS_URL", "redis://redis:6379/0")


settings = Settings()
