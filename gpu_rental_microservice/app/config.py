from pydantic import BaseModel
import os

class Settings(BaseModel):
    app_name: str = "gpu-rental-microservice"
    app_env: str = os.getenv("APP_ENV", "dev")
    db_path: str = os.getenv("DB_PATH", "./gpu_rental.db")
    docs_enabled: bool = os.getenv("DOCS_ENABLED", "true").lower() == "true"
    default_currency: str = "EUR"
    secure_headers: bool = True

settings = Settings()
