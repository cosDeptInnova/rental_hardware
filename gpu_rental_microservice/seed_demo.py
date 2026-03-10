from app.db import init_db, upsert_client
from app.security import hash_api_key

def main():
    init_db()
    plain_key = "demo-client-key-001"
    upsert_client(
        client_name="cliente-poc-01",
        api_key_hash=hash_api_key(plain_key),
        scopes="jobs:write,jobs:read,usage:read",
        plan_name="poc-dedicada-media-jornada",
        requests_per_minute=30,
        max_concurrent_jobs=2,
        max_job_seconds=120,
        max_input_bytes=2_000_000,
        monthly_credit_limit=50_000.0,
        price_per_gpu_second=0.0025,
        gpu_share=1.0,
        is_admin=1,
    )
    print("Demo client created")
    print(f"API key: {plain_key}")

if __name__ == "__main__":
    main()
