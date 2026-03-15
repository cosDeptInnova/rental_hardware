from fastapi.testclient import TestClient
from apps.bastion_control_plane.main import app


def test_auth_required():
    client = TestClient(app)
    r = client.get('/v1/catalog')
    assert r.status_code == 401
