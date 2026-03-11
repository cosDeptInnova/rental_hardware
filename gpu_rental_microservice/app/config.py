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

    enable_api_key_auth: bool = os.getenv("ENABLE_API_KEY_AUTH", "true").lower() == "true"
    enable_jwt_auth: bool = os.getenv("ENABLE_JWT_AUTH", "false").lower() == "true"
    jwt_secret: str = os.getenv("JWT_SECRET", "")
    jwt_issuer: str | None = os.getenv("JWT_ISSUER")
    jwt_audience: str | None = os.getenv("JWT_AUDIENCE")

    enable_mtls_auth: bool = os.getenv("ENABLE_MTLS_AUTH", "false").lower() == "true"
    mtls_fingerprint_header: str = os.getenv("MTLS_FINGERPRINT_HEADER", "X-Client-Cert-Fingerprint")

    api_key_ttl_days: int = int(os.getenv("API_KEY_TTL_DAYS", "90"))
    failed_auth_alert_threshold: int = int(os.getenv("FAILED_AUTH_ALERT_THRESHOLD", "5"))
    failed_auth_alert_window_seconds: int = int(os.getenv("FAILED_AUTH_ALERT_WINDOW_SECONDS", "300"))


settings = Settings()
