from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import create_app
from app.services.session_control import session_control


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


def test_revoke_session_blocks_requests(monkeypatch) -> None:
    from app.api import routes_jobs

    monkeypatch.setattr(routes_jobs, "NvmlMonitor", FakeNvmlMonitor)
    app = create_app()
    client = TestClient(app)

    tenant_resp = client.post("/v1/admin/tenants", headers=ADMIN_HEADERS, json={"name": "tenant-revoke"})
    tenant = tenant_resp.json()

    client.post(
        "/v1/admin/reservations",
        headers=ADMIN_HEADERS,
        json={
            "tenant_id": tenant["tenant_id"],
            "reserved_vram_mb": 8192,
            "max_concurrency": 2,
            "priority": 80,
            "allowed_services": ["inference"],
            "preemptive": True,
            "enabled": True,
        },
    )

    revoke_resp = client.post(f"/v1/admin/sessions/{tenant['tenant_id']}/revoke", headers=ADMIN_HEADERS)
    assert revoke_resp.status_code == 200

    blocked = client.post(
        "/v1/inference",
        headers={"X-API-Key": tenant["api_key"]},
        json={"model": "mistral", "requested_vram_mb": 1024, "priority": 50, "payload": {"messages": []}},
    )
    assert blocked.status_code == 401
    assert blocked.json()["detail"] == "session_revoked"

    session_control.restore(tenant["tenant_id"])
