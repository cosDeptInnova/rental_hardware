from __future__ import annotations

from fastapi.testclient import TestClient

from app.core.db import SessionLocal
from app.core.models import Job, RequestMetric, Reservation, Tenant
from app.main import create_app


ADMIN_HEADERS = {"X-Admin-Token": "change-me"}


class FakeNvmlMonitor:
    available = True

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def snapshots(self):
        from app.gpu.nvml_monitor import GpuSnapshot

        return [
            GpuSnapshot(
                index=0,
                name="L40S",
                uuid="gpu-0",
                total_mb=49152,
                used_mb=10000,
                free_mb=39152,
                gpu_util=25,
                processes=[],
            )
        ]


def _cleanup_tables() -> None:
    with SessionLocal() as db:
        db.query(RequestMetric).delete()
        db.query(Job).delete()
        db.query(Reservation).delete()
        db.query(Tenant).delete()
        db.commit()


def test_inference_and_analytics_summary(monkeypatch) -> None:
    from app.api import routes_jobs

    monkeypatch.setattr(routes_jobs, "NvmlMonitor", FakeNvmlMonitor)
    _cleanup_tables()

    app = create_app()
    client = TestClient(app)

    tenant_resp = client.post("/v1/admin/tenants", headers=ADMIN_HEADERS, json={"name": "tenant-analytics"})
    assert tenant_resp.status_code == 201
    tenant_body = tenant_resp.json()

    reservation_payload = {
        "tenant_id": tenant_body["tenant_id"],
        "reserved_vram_mb": 12288,
        "max_concurrency": 5,
        "priority": 80,
        "allowed_services": ["inference", "embeddings"],
        "preemptive": True,
        "enabled": True,
    }
    reservation_resp = client.post("/v1/admin/reservations", headers=ADMIN_HEADERS, json=reservation_payload)
    assert reservation_resp.status_code == 200

    tenant_headers = {"X-API-Key": tenant_body["api_key"]}
    inference_payload = {
        "model": "mistral-7b-instruct",
        "requested_vram_mb": 8192,
        "priority": 50,
        "payload": {
            "messages": [{"role": "user", "content": "Hola"}],
            "temperature": 0.2,
        },
    }
    inference_resp = client.post("/v1/inference", headers=tenant_headers, json=inference_payload)
    assert inference_resp.status_code == 200
    body = inference_resp.json()
    assert body["service_type"] == "inference"
    assert body["state"] == "finished"

    analytics_resp = client.get("/v1/analytics/summary", headers=tenant_headers)
    assert analytics_resp.status_code == 200
    analytics = analytics_resp.json()
    assert analytics["requests_total"] == 1
    assert analytics["success_total"] == 1
    assert analytics["failed_total"] == 0
    assert analytics["finished_total"] >= 1
    assert analytics["total_tokens_total"] > 0
    assert analytics["by_service"][0]["service_type"] == "inference"
