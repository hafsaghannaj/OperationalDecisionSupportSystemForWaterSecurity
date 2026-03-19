from types import SimpleNamespace

from fastapi.testclient import TestClient

from services.api.app.db import get_db_session
from services.api.app.main import app


client = TestClient(app)


class FakeSettings:
    api_key = ""


class FakeSession:
    def commit(self) -> None:
        return None

    def refresh(self, _record) -> None:
        return None


def test_audit_logs_endpoint(monkeypatch) -> None:
    monkeypatch.setattr(
        "services.api.app.main.list_audit_logs",
        lambda _session, region_id=None, limit=25: [
            SimpleNamespace(
                id="evt-1",
                action_type="alert_acknowledged",
                target_type="alert_event",
                target_id="BD-4047:2026-W10",
                operator_id="ops-1",
                region_id="BD-4047",
                week="2026-W10",
                model_version=None,
                note="Review opened.",
                event_metadata={"status": "acknowledged"},
                created_at="2026-03-19T17:00:00+00:00",
            )
        ],
    )

    response = client.get("/audit/logs")

    assert response.status_code == 200
    assert response.json()[0]["action_type"] == "alert_acknowledged"


def test_acknowledge_alert_endpoint(monkeypatch) -> None:
    monkeypatch.setattr("services.api.app.main.get_settings", lambda: FakeSettings())
    monkeypatch.setattr("services.api.app.main.acknowledge_alert", lambda _session, region_id, week: object())
    monkeypatch.setattr("services.api.app.main.record_audit_event", lambda *args, **kwargs: None)
    app.dependency_overrides[get_db_session] = lambda: FakeSession()
    try:
        response = client.post("/alerts/BD-4047/2026-W10/acknowledge")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["status"] == "acknowledged"


def test_field_action_endpoint(monkeypatch) -> None:
    monkeypatch.setattr("services.api.app.main.get_settings", lambda: FakeSettings())
    monkeypatch.setattr(
        "services.api.app.main.record_audit_event",
        lambda *args, **kwargs: SimpleNamespace(
            id="evt-2",
            action_type="field_action_noted",
            target_type="field_action",
            target_id="BD-4047:2026-W10:chlorination",
            operator_id="ops-2",
            region_id="BD-4047",
            week_start_date=None,
            model_version=None,
            note="Tablets dispatched.",
            event_metadata={"action": "chlorination"},
            created_at=SimpleNamespace(isoformat=lambda: "2026-03-19T18:00:00+00:00"),
        ),
    )
    app.dependency_overrides[get_db_session] = lambda: FakeSession()
    try:
        response = client.post(
            "/field-actions",
            json={
                "region_id": "BD-4047",
                "week": "2026-W10",
                "operator_id": "ops-2",
                "action": "chlorination",
                "note": "Tablets dispatched.",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["action_type"] == "field_action_noted"
