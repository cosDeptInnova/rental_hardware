from __future__ import annotations

from fastapi.testclient import TestClient

from app.core.auth import hash_api_key
from app.core.db import SessionLocal
from app.core.models import Reservation, Tenant
from app.main import create_app


ADMIN_HEADERS = {"X-Admin-Token": "change-me"}


def _cleanup_tables() -> None:
    with SessionLocal() as db:
        db.query(Reservation).delete()
        db.query(Tenant).delete()
        db.commit()


def test_create_tenant_returns_api_key_and_stores_hash() -> None:
    _cleanup_tables()
    app = create_app()
    client = TestClient(app)

    response = client.post("/v1/admin/tenants", headers=ADMIN_HEADERS, json={"name": "acme"})

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "acme"
    assert body["tenant_id"]
    assert body["api_key"]

    with SessionLocal() as db:
        tenant = db.get(Tenant, body["tenant_id"])
        assert tenant is not None
        assert tenant.name == "acme"
        assert tenant.api_key_hash == hash_api_key(body["api_key"])
        assert tenant.api_key_hash != body["api_key"]


def test_create_reservation_for_tenant() -> None:
    _cleanup_tables()
    app = create_app()
    client = TestClient(app)

    tenant_resp = client.post("/v1/admin/tenants", headers=ADMIN_HEADERS, json={"name": "tenant-2"})
    tenant_id = tenant_resp.json()["tenant_id"]

    reservation_payload = {
        "tenant_id": tenant_id,
        "reserved_vram_mb": 8192,
        "max_concurrency": 2,
        "priority": 80,
        "allowed_services": ["inference", "embeddings"],
        "preemptive": True,
        "enabled": True,
    }

    response = client.post("/v1/admin/reservations", headers=ADMIN_HEADERS, json=reservation_payload)

    assert response.status_code == 200
    body = response.json()
    assert body["tenant_id"] == tenant_id
    assert body["reserved_vram_mb"] == 8192
    assert body["allowed_services"] == ["inference", "embeddings"]


def test_capacity_returns_503_when_nvml_unavailable(monkeypatch) -> None:
    from app.api import routes_admin

    class FakeNvmlMonitor:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        @property
        def available(self) -> bool:
            return False

    monkeypatch.setattr(routes_admin, "NvmlMonitor", FakeNvmlMonitor)

    app = create_app()
    client = TestClient(app)

    response = client.get("/v1/admin/capacity", headers=ADMIN_HEADERS)

    assert response.status_code == 503
    assert "nvml_unavailable" in response.json()["detail"]
