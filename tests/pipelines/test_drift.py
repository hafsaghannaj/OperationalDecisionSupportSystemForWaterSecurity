from types import SimpleNamespace

from libs.ml.drift import DriftPolicy, assess_feature_drift, build_feature_profile


def make_row(**overrides):
    payload = {
        "rainfall_total_mm_7d": 40.0,
        "rainfall_anomaly_zscore": 0.0,
        "population_total": 1500000.0,
        "population_density_km2": 700.0,
        "wash_access_basic_water_pct": 90.0,
        "wash_access_basic_sanitation_pct": 85.0,
        "lag_case_count_1w": 1,
        "rolling_case_count_4w": 2,
    }
    payload.update(overrides)
    return SimpleNamespace(**payload)


def test_assess_feature_drift_flags_shifted_feature_window() -> None:
    training_rows = [
        make_row(rainfall_total_mm_7d=38.0, rainfall_anomaly_zscore=-0.1),
        make_row(rainfall_total_mm_7d=40.0, rainfall_anomaly_zscore=0.0),
        make_row(rainfall_total_mm_7d=42.0, rainfall_anomaly_zscore=0.1),
        make_row(rainfall_total_mm_7d=41.0, rainfall_anomaly_zscore=0.1),
    ]
    scoring_rows = [
        make_row(rainfall_total_mm_7d=68.0, rainfall_anomaly_zscore=2.1),
        make_row(rainfall_total_mm_7d=72.0, rainfall_anomaly_zscore=2.4),
        make_row(rainfall_total_mm_7d=70.0, rainfall_anomaly_zscore=2.3),
    ]

    drift = assess_feature_drift(
        build_feature_profile(training_rows),
        scoring_rows,
        policy=DriftPolicy(warn_shift_score=1.0, fail_shift_score=2.0),
    )

    assert drift.status == "failed"
    assert drift.failed_features >= 1
    assert drift.top_drift_features[0].feature in {"rainfall_total_mm_7d", "rainfall_anomaly_zscore"}


def test_assess_feature_drift_skips_without_training_profile() -> None:
    drift = assess_feature_drift(
        None,
        [make_row(), make_row(), make_row()],
    )

    assert drift.status == "skipped"
    assert "no training feature profile" in drift.message.lower()
