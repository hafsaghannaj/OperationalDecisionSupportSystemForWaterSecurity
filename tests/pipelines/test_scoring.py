from types import SimpleNamespace

from pipelines.scoring.weekly import (
    build_driver_contributions,
    derive_severity,
    recommended_action_for_severity,
    score_feature,
)


def make_feature(**overrides):
    payload = {
        "rainfall_total_mm_7d": 40.0,
        "rainfall_anomaly_zscore": 0.0,
        "population_total": 1500000.0,
        "wash_access_basic_sanitation_pct": 85.0,
        "wash_access_basic_water_pct": 90.0,
        "lag_case_count_1w": 1,
        "rolling_case_count_4w": 2,
        "population_density_km2": 700.0,
        "quality_flag": "ok",
    }
    payload.update(overrides)
    return SimpleNamespace(**payload)


def test_build_driver_contributions_prefers_higher_pressure_signals() -> None:
    high_pressure = make_feature(
        rainfall_anomaly_zscore=2.1,
        wash_access_basic_sanitation_pct=58.0,
        lag_case_count_1w=18,
        rolling_case_count_4w=46,
        population_density_km2=3100.0,
    )
    low_pressure = make_feature()

    high_contributions = build_driver_contributions(high_pressure)
    low_contributions = build_driver_contributions(low_pressure)

    assert sum(high_contributions.values()) > sum(low_contributions.values())


def test_score_feature_yields_higher_score_for_higher_pressure_case() -> None:
    high_pressure = make_feature(
        rainfall_anomaly_zscore=2.4,
        wash_access_basic_sanitation_pct=52.0,
        wash_access_basic_water_pct=71.0,
        lag_case_count_1w=22,
        rolling_case_count_4w=58,
        population_density_km2=4200.0,
    )
    low_pressure = make_feature(
        rainfall_anomaly_zscore=0.1,
        wash_access_basic_sanitation_pct=93.0,
        wash_access_basic_water_pct=97.0,
        lag_case_count_1w=0,
        rolling_case_count_4w=0,
        population_density_km2=400.0,
    )

    high_score = score_feature(high_pressure)
    low_score = score_feature(low_pressure)

    assert high_score.score > low_score.score
    assert high_score.severity in {"medium", "high"}
    assert low_score.severity == "low"


def test_derive_severity_thresholds() -> None:
    assert derive_severity(0.75) == "high"
    assert derive_severity(0.4) == "medium"
    assert derive_severity(0.39) == "low"


def test_recommended_action_for_severity() -> None:
    action, status = recommended_action_for_severity("high")
    assert "field verification" in action.lower()
    assert status == "open"

    action, status = recommended_action_for_severity("low")
    assert "routine monitoring" in action.lower()
    assert status == "resolved"


def test_score_feature_uses_promoted_model_when_available() -> None:
    class StubEstimator:
        def predict_proba(self, rows):
            assert len(rows) == 1
            assert rows[0][0] == 40.0
            return [[0.18, 0.82]]

    promoted_model = SimpleNamespace(
        estimator=StubEstimator(),
        feature_columns=(
            "rainfall_total_mm_7d",
            "rainfall_anomaly_zscore",
            "population_total",
            "population_density_km2",
            "wash_access_basic_water_pct",
            "wash_access_basic_sanitation_pct",
            "lag_case_count_1w",
            "rolling_case_count_4w",
        ),
        metadata={},
        model_version="baseline-logreg-test",
    )

    scored = score_feature(make_feature(), promoted_model=promoted_model)

    assert scored.score == 0.82
    assert scored.severity == "high"


def test_score_feature_uses_promoted_alert_thresholds_when_available() -> None:
    class StubEstimator:
        def predict_proba(self, rows):
            assert len(rows) == 1
            return [[0.38, 0.62]]

    promoted_model = SimpleNamespace(
        estimator=StubEstimator(),
        feature_columns=(
            "rainfall_total_mm_7d",
            "rainfall_anomaly_zscore",
            "population_total",
            "population_density_km2",
            "wash_access_basic_water_pct",
            "wash_access_basic_sanitation_pct",
            "lag_case_count_1w",
            "rolling_case_count_4w",
        ),
        metadata={"alert_thresholds": {"medium": 0.55, "high": 0.8}},
        model_version="baseline-logreg-test",
    )

    scored = score_feature(make_feature(), promoted_model=promoted_model)

    assert scored.score == 0.62
    assert scored.severity == "medium"
