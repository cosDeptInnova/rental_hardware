from fastapi.testclient import TestClient
from apps.gpu_agent.main import app


def test_internal_auth():
    with TestClient(app) as client:
        r = client.get('/internal/models/inventory')
        assert r.status_code == 401
