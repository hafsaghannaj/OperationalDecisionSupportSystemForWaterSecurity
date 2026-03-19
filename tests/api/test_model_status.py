from fastapi.testclient import TestClient

from services.api.app.main import app
from services.api.app.models import DriftStatus, FeatureDriftDetail, FreshnessStatus, ModelMetricSummary, ModelStatus


client = TestClient(app)


def test_model_status_endpoint(monkeypatch) -> None:
    def fake_load_model_status() -> ModelStatus:
        return ModelStatus(
            status="promoted",
            model_version="baseline-logreg-20260319T120000Z",
            model_family="logistic_regression",
            trained_at="2026-03-19T12:00:00+00:00",
            promoted_at="2026-03-19T12:05:00+00:00",
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
            model_card_path="/tmp/baseline-logreg-20260319T120000Z.md",
            training_data_freshness=FreshnessStatus(
                scope="training_data",
                status="warning",
                latest_week="2026-03-09",
                reference_date="2026-03-19",
                age_days=10,
                warn_after_days=7,
                fail_after_days=30,
                message="Training data latest week 2026-03-09 is 10 day(s) old against reference date 2026-03-19 and is outside the preferred freshness window.",
            ),
            scoring_feature_drift=DriftStatus(
                scope="scoring_feature_drift",
                status="warning",
                rows=3,
                compared_features=8,
                warning_features=1,
                failed_features=0,
                message="Feature drift check warned on 1 feature(s); latest window is shifting away from training.",
                top_drift_features=[
                    FeatureDriftDetail(
                        feature="rainfall_total_mm_7d",
                        status="warning",
                        training_mean=44.0,
                        current_mean=63.0,
                        shift_score=1.4,
                        missing_rate_delta=0.0,
                        message="rainfall_total_mm_7d: shift score 1.40 exceeds warning threshold 1.00.",
                    )
                ],
            ),
        )

    monkeypatch.setattr("services.api.app.main.load_model_status", fake_load_model_status)

    response = client.get("/model/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["model_version"] == "baseline-logreg-20260319T120000Z"
    assert payload["promoted_at"] == "2026-03-19T12:05:00+00:00"
    assert payload["evaluation"]["average_precision"] == 0.88
    assert payload["persistence_baseline"]["average_precision"] == 0.74
    assert payload["training_data_freshness"]["status"] == "warning"
    assert payload["scoring_feature_drift"]["status"] == "warning"
    assert payload["scoring_feature_drift"]["top_drift_features"][0]["feature"] == "rainfall_total_mm_7d"
