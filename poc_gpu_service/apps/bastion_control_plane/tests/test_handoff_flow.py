from fastapi.testclient import TestClient

from apps.bastion_control_plane.main import app
from apps.bastion_control_plane.api import routes


def test_handoff_on_lease_create(monkeypatch):
    async def fake_on_lease_create(**kwargs):
        return {"release": {"target_reached": True}, "snapshot": {"snapshot_id": "s1"}}

    async def fake_call(method, path, payload=None):
        if path == "/internal/backends/start":
            return {"instance_id": "b1", "pid": 123, "host": "127.0.0.1", "port": 9001, "status": "running"}
        raise AssertionError(path)

    monkeypatch.setattr(routes.capacity_manager, "on_lease_create", fake_on_lease_create)
    monkeypatch.setattr(routes.client, "call", fake_call)

    with TestClient(app) as client:
        r = client.post("/v1/leases", headers={"X-API-Key": "client1_key_123"}, json={"model_alias": "llama3-8b-instruct", "task_type": "chat", "requested_gpu": "CUDA0"})
        assert r.status_code == 200
        assert r.json()["handoff"]["snapshot"]["snapshot_id"] == "s1"


def test_handoff_on_lease_close(monkeypatch):
    async def fake_call(method, path, payload=None):
        if path == "/internal/backends/start":
            return {"instance_id": "b2", "pid": 123, "host": "127.0.0.1", "port": 9001, "status": "running"}
        if path == "/internal/backends/stop":
            return {"ok": True}
        raise AssertionError(path)

    async def fake_restore(lease_id):
        return {"ok": True, "lease_id": lease_id}

    async def fake_create(**kwargs):
        return {"release": {"target_reached": True}}

    monkeypatch.setattr(routes.client, "call", fake_call)
    monkeypatch.setattr(routes.capacity_manager, "on_lease_close", fake_restore)
    monkeypatch.setattr(routes.capacity_manager, "on_lease_create", fake_create)

    with TestClient(app) as client:
        created = client.post("/v1/leases", headers={"X-API-Key": "client1_key_123"}, json={"model_alias": "llama3-8b-instruct", "task_type": "chat", "requested_gpu": "CUDA0"})
        lease_id = created.json()["lease_id"]
        closed = client.post("/v1/leases/close", headers={"X-API-Key": "client1_key_123"}, json={"lease_id": lease_id})
        assert closed.status_code == 200
        assert closed.json()["restore"]["ok"] is True


def test_handoff_insufficient_safe_capacity(monkeypatch):
    async def fake_on_lease_create(**kwargs):
        return {"release": {"target_reached": False, "error_code": "insufficient_safe_capacity"}}

    monkeypatch.setattr(routes.capacity_manager, "on_lease_create", fake_on_lease_create)

    with TestClient(app) as client:
        r = client.post(
            "/v1/leases",
            headers={"X-API-Key": "client1_key_123"},
            json={"model_alias": "llama3-8b-instruct", "task_type": "chat", "requested_gpu": "CUDA0"},
        )
        assert r.status_code == 409
        assert r.json()["detail"]["handoff"]["release"]["error_code"] == "insufficient_safe_capacity"
