from types import SimpleNamespace

from fastapi.testclient import TestClient

from services.api.app.auth import create_operator_token, verify_operator_token
from services.api.app.db import get_db_session
from services.api.app.main import app


client = TestClient(app)


class FakeSession:
    def commit(self) -> None:
        return None

    def refresh(self, _record) -> None:
        return None


class SecretSettings:
    api_key = ""
    auth_token_secret = "top-secret"
    auth_issuer = "odssws"
    auth_audience = "odssws-operators"
    allow_legacy_api_key = False


def test_operator_token_round_trip() -> None:
    token = create_operator_token(
        operator_id="ops-1",
        roles=["operator", "admin"],
        secret="top-secret",
        issuer="odssws",
        audience="odssws-operators",
    )

    actor = verify_operator_token(
        token,
        secret="top-secret",
        issuer="odssws",
        audience="odssws-operators",
    )

    assert actor.operator_id == "ops-1"
    assert actor.has_any_role(("admin",))


def test_acknowledge_requires_bearer_when_secret_configured(monkeypatch) -> None:
    monkeypatch.setattr("services.api.app.main.get_settings", lambda: SecretSettings())
    app.dependency_overrides[get_db_session] = lambda: FakeSession()
    try:
        response = client.post("/alerts/BD-4047/2026-W10/acknowledge")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 401
    assert "bearer token" in response.json()["detail"].lower()


def test_acknowledge_accepts_operator_bearer_token(monkeypatch) -> None:
    captured: dict[str, str | None] = {}

    def fake_record_audit_event(*_args, **kwargs):
        captured["operator_id"] = kwargs.get("operator_id")
        return None

    token = create_operator_token(
        operator_id="ops-7",
        roles=["operator"],
        secret=SecretSettings.auth_token_secret,
        issuer=SecretSettings.auth_issuer,
        audience=SecretSettings.auth_audience,
    )

    monkeypatch.setattr("services.api.app.main.get_settings", lambda: SecretSettings())
    monkeypatch.setattr("services.api.app.main.acknowledge_alert", lambda _session, region_id, week: object())
    monkeypatch.setattr("services.api.app.main.record_audit_event", fake_record_audit_event)
    app.dependency_overrides[get_db_session] = lambda: FakeSession()
    try:
        response = client.post(
            "/alerts/BD-4047/2026-W10/acknowledge",
            headers={"Authorization": f"Bearer {token}"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert captured["operator_id"] == "ops-7"


def test_promote_requires_admin_role(monkeypatch) -> None:
    token = create_operator_token(
        operator_id="ops-8",
        roles=["operator"],
        secret=SecretSettings.auth_token_secret,
        issuer=SecretSettings.auth_issuer,
        audience=SecretSettings.auth_audience,
    )

    monkeypatch.setattr("services.api.app.main.get_settings", lambda: SecretSettings())
    monkeypatch.setattr(
        "services.api.app.main.promote_registered_model_run",
        lambda *_args, **_kwargs: SimpleNamespace(
            model_version="baseline-logreg-test",
            status="promoted",
            message="ok",
            previous_active_model_version=None,
        ),
    )
    app.dependency_overrides[get_db_session] = lambda: FakeSession()
    try:
        response = client.post(
            "/model/runs/baseline-logreg-test/promote",
            headers={"Authorization": f"Bearer {token}"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403
