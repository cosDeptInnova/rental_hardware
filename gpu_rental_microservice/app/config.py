from pydantic import BaseModel
import os

class Settings(BaseModel):
    app_name: str = "gpu-rental-microservice"
    app_env: str = os.getenv("APP_ENV", "dev")
    db_path: str = os.getenv("DB_PATH", "./gpu_rental.db")
    docs_enabled: bool = os.getenv("DOCS_ENABLED", "true").lower() == "true"
    default_currency: str = "EUR"
    price_per_1k_tokens: float = float(os.getenv("PRICE_PER_1K_TOKENS", "0.002"))
    price_per_kwh: float = float(os.getenv("PRICE_PER_KWH", "0.25"))
    secure_headers: bool = True

settings = Settings()
