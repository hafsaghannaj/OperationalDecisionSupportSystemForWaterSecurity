from fastapi.testclient import TestClient

from services.api.app.main import app


client = TestClient(app)


def test_pilot_endpoint_returns_locked_definition() -> None:
    response = client.get("/pilot")

    assert response.status_code == 200
    payload = response.json()
    assert payload["country"] == "Bangladesh"
    assert payload["admin_level"] == "ADM2"
    assert payload["data_sources"][0]["status"] == "live"


def test_demo_risk_points_endpoint_returns_points() -> None:
    response = client.get("/demo/risk-points")

    assert response.status_code == 200
    payload = response.json()
    assert payload
    assert payload[0]["region_id"].startswith("BD-")
    assert payload[0]["risk_score"] >= 0
