from fastapi.testclient import TestClient

from services.api.app.main import app


client = TestClient(app)


def test_main_api_includes_cag_route() -> None:
    response = client.post(
        "/cag/ask",
        json={"question": "What actions are recommended at elevated risk?"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["cache_type"] == "general"
    assert "Priority guidance" in payload["answer"]
