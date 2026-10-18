from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_endpoint_does_not_need_stockfish_or_auth():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_root_points_to_docs():
    response = client.get("/")
    assert response.status_code == 200
    assert response.json()["docs"] == "/docs"
