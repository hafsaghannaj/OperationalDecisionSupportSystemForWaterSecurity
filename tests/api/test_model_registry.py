from fastapi.testclient import TestClient

from services.api.app.main import app
from services.api.app.models import (
    FreshnessStatus,
    ModelComparison,
    ModelMetricSummary,
    ModelPromotionResponse,
    ModelRunSummary,
)


client = TestClient(app)


def sample_run(*, model_version: str, registry_status: str, promotion_status: str) -> ModelRunSummary:
    return ModelRunSummary(
        model_version=model_version,
        model_family="logistic_regression",
        registry_status=registry_status,
        promotion_status=promotion_status,
        trained_at="2026-03-19T12:00:00+00:00",
        promoted_at="2026-03-19T12:05:00+00:00" if registry_status == "active" else None,
        feature_build_version="sample-v1",
        training_rows=12,
        training_weeks=4,
        evaluation_splits=2,
        evaluation=ModelMetricSummary(
            average_precision=0.88,
            roc_auc=0.91,
            brier_score=0.12,
            positive_rate=0.5,
        ),
        persistence_baseline=ModelMetricSummary(
            average_precision=0.74,
            roc_auc=0.8,
            brier_score=0.19,
            positive_rate=0.5,
        ),
        training_data_freshness=FreshnessStatus(
            scope="training_data",
            status="ok",
            latest_week="2026-03-09",
            reference_date="2026-03-19",
            age_days=10,
            warn_after_days=14,
            fail_after_days=30,
            message="Freshness is within the configured operational window.",
        ),
        alert_thresholds={"medium": 0.42, "high": 0.71},
        promotion_reasons=[] if promotion_status == "eligible" else ["AUCPR below threshold."],
        model_card_path=f"/tmp/{model_version}.md",
    )


def test_model_compare_endpoint(monkeypatch) -> None:
    def fake_load_model_comparison(_session) -> ModelComparison:
        return ModelComparison(
            active_model=sample_run(
                model_version="baseline-logreg-20260319T120000Z",
                registry_status="active",
                promotion_status="eligible",
            ),
            challenger_model=sample_run(
                model_version="baseline-lightgbm-20260319T123000Z",
                registry_status="challenger",
                promotion_status="eligible",
            ),
            recent_runs=[
                sample_run(
                    model_version="baseline-lightgbm-20260319T123000Z",
                    registry_status="challenger",
                    promotion_status="eligible",
                ),
                sample_run(
                    model_version="baseline-logreg-20260319T120000Z",
                    registry_status="active",
                    promotion_status="eligible",
                ),
            ],
        )

    monkeypatch.setattr("services.api.app.main.load_model_comparison", fake_load_model_comparison)

    response = client.get("/model/compare")

    assert response.status_code == 200
    payload = response.json()
    assert payload["active_model"]["registry_status"] == "active"
    assert payload["challenger_model"]["model_version"] == "baseline-lightgbm-20260319T123000Z"
    assert payload["recent_runs"][0]["promotion_status"] == "eligible"


def test_promote_model_endpoint(monkeypatch) -> None:
    class FakeSettings:
        api_key = ""

    def fake_promote_model_run(_session, model_version: str) -> ModelPromotionResponse:
        return ModelPromotionResponse(
            model_version=model_version,
            status="promoted",
            message="Model has been promoted to the active champion.",
            previous_active_model_version="baseline-logreg-20260319T120000Z",
        )

    monkeypatch.setattr("services.api.app.main.promote_registered_model_run", fake_promote_model_run)
    monkeypatch.setattr("services.api.app.main.get_settings", lambda: FakeSettings())

    response = client.post("/model/runs/baseline-lightgbm-20260319T123000Z/promote")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "promoted"
    assert payload["previous_active_model_version"] == "baseline-logreg-20260319T120000Z"
