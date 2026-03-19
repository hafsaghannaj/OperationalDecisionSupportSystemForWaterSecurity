from fastapi.testclient import TestClient

from services.api.app.main import app
from services.api.app.models import AlertVolumeStatus, DriftStatus, FeatureDriftDetail, FreshnessStatus, ScoringHealth, ScoringRunSummary


client = TestClient(app)


def sample_scoring_run() -> ScoringRunSummary:
    return ScoringRunSummary(
        run_scope="latest_week",
        run_status="warning",
        executed_at="2026-03-19T14:20:00+00:00",
        model_version="baseline-logreg-20260319T120000Z",
        feature_build_version="sample-v1",
        latest_week="2026-03-09",
        weeks_scored=1,
        rows_scored=3,
        rows_inserted=0,
        rows_updated=3,
        alerts_created_or_updated=2,
        alerts_removed=1,
        medium_or_higher_alerts=2,
        high_alerts=1,
        medium_or_higher_alert_rate=0.6667,
        high_alert_rate=0.3333,
        average_score=0.54,
        max_score=0.81,
        non_ok_quality_rows=1,
        feature_freshness=FreshnessStatus(
            scope="scoring_features",
            status="ok",
            latest_week="2026-03-09",
            reference_date="2026-03-19",
            age_days=10,
            warn_after_days=14,
            fail_after_days=45,
            message="Scoring features freshness check ok.",
        ),
        feature_drift=DriftStatus(
            scope="scoring_feature_drift",
            status="warning",
            rows=3,
            compared_features=8,
            warning_features=1,
            failed_features=0,
            message="Feature drift check warned on 1 feature(s).",
            top_drift_features=[
                FeatureDriftDetail(
                    feature="rainfall_total_mm_7d",
                    status="warning",
                    training_mean=44.0,
                    current_mean=63.0,
                    shift_score=1.4,
                    missing_rate_delta=0.0,
                    message="rainfall_total_mm_7d warning.",
                )
            ],
        ),
        alert_volume=AlertVolumeStatus(
            scope="scoring_alert_volume",
            status="warning",
            rows=3,
            medium_or_higher_alerts=2,
            high_alerts=1,
            medium_or_higher_alert_rate=0.6667,
            high_alert_rate=0.3333,
            expected_medium_or_higher_alert_rate=0.4,
            expected_high_alert_rate=0.15,
            medium_or_higher_rate_delta=0.2667,
            high_alert_rate_delta=0.1833,
            warn_rate_delta=0.15,
            fail_rate_delta=0.3,
            message="Alert-volume check warning.",
        ),
    )


def test_scoring_health_endpoint(monkeypatch) -> None:
    def fake_load_scoring_health(_session) -> ScoringHealth:
        run = sample_scoring_run()
        return ScoringHealth(latest_run=run, recent_runs=[run])

    monkeypatch.setattr("services.api.app.main.load_scoring_health", fake_load_scoring_health)

    response = client.get("/scoring/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["latest_run"]["run_status"] == "warning"
    assert payload["latest_run"]["alert_volume"]["status"] == "warning"
    assert payload["latest_run"]["medium_or_higher_alerts"] == 2
    assert payload["recent_runs"][0]["run_scope"] == "latest_week"
