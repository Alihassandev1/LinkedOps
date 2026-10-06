# tests/test_health.py
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_docs_available():
    response = client.get("/docs")
    assert response.status_code == 200

def test_unknown_route_returns_404():
    response = client.get("/does-not-exist")
    assert response.status_code == 404