from fastapi.testclient import TestClient

from outbreaks.cag.api import app


client = TestClient(app)


def test_cag_ask_endpoint_returns_answer() -> None:
    response = client.post(
        "/cag/ask",
        json={"question": "What actions are recommended at elevated risk?"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["cache_type"] == "general"
    assert payload["used_region"] is None
    assert "Priority guidance" in payload["answer"]


def test_cag_ask_endpoint_uses_region_cache() -> None:
    response = client.post(
        "/cag/ask",
        json={"question": "How should we plan river delta operations?", "region_key": "example_region"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["cache_type"] == "region"
    assert payload["used_region"] == "example_region"
