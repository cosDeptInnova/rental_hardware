from sqlalchemy import select
from apps.bastion_control_plane.db.session import engine, SessionLocal
from apps.bastion_control_plane.models.db_models import Base, Tenant, ApiKey


def init_db_and_seed() -> None:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        if not db.scalar(select(Tenant).where(Tenant.tenant_id == "interno")):
            db.add(Tenant(tenant_id="interno", name="Tenant interno"))
        if not db.scalar(select(Tenant).where(Tenant.tenant_id == "cliente1")):
            db.add(Tenant(tenant_id="cliente1", name="Cliente 1"))
        if not db.scalar(select(ApiKey).where(ApiKey.key == "internal_key_456")):
            db.add(ApiKey(key="internal_key_456", tenant_id="interno"))
        if not db.scalar(select(ApiKey).where(ApiKey.key == "client1_key_123")):
            db.add(ApiKey(key="client1_key_123", tenant_id="cliente1"))
        db.commit()
    finally:
        db.close()
