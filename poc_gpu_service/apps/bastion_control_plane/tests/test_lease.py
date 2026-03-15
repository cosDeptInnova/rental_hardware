from fastapi.testclient import TestClient
from apps.bastion_control_plane.main import app


def test_list_catalog_ok():
    client = TestClient(app)
    r = client.get('/v1/catalog', headers={'X-API-Key':'client1_key_123'})
    assert r.status_code == 200
    assert 'models' in r.json()
