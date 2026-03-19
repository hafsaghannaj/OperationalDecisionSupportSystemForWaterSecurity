from fastapi.testclient import TestClient

from services.api.app.main import app
from services.api.app.models import ModelCardDocument


client = TestClient(app)


def test_model_card_endpoint(monkeypatch) -> None:
    def fake_load_model_card() -> ModelCardDocument:
        return ModelCardDocument(
            model_version="baseline-logreg-20260319T120000Z",
            promoted_at="2026-03-19T12:05:00+00:00",
            content="# Model Card\n\n## Model Summary\n\n- Version: baseline-logreg-20260319T120000Z\n",
        )

    monkeypatch.setattr("services.api.app.main.load_model_card", fake_load_model_card)

    response = client.get("/model/card")

    assert response.status_code == 200
    payload = response.json()
    assert payload["model_version"] == "baseline-logreg-20260319T120000Z"
    assert payload["format"] == "markdown"
    assert "# Model Card" in payload["content"]


def test_model_card_endpoint_returns_404_when_missing(monkeypatch) -> None:
    monkeypatch.setattr("services.api.app.main.load_model_card", lambda: None)

    response = client.get("/model/card")

    assert response.status_code == 404
