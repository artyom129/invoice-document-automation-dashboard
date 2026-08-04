from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"

def test_dashboard():
    response = client.get("/")
    assert response.status_code == 200
    assert "Invoice processing dashboard" in response.text

def test_api_invoices():
    response = client.get("/api/invoices")
    assert response.status_code == 200
    assert isinstance(response.json(), list)
