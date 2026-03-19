from datetime import date

from libs.ml.freshness import FreshnessPolicy, assess_latest_week_freshness


def test_assess_latest_week_freshness_reports_ok() -> None:
    check = assess_latest_week_freshness(
        date(2026, 3, 9),
        scope="training_data",
        reference_date=date(2026, 3, 12),
        policy=FreshnessPolicy(warn_after_days=7, fail_after_days=21),
    )

    assert check.status == "ok"
    assert check.age_days == 3


def test_assess_latest_week_freshness_reports_warning() -> None:
    check = assess_latest_week_freshness(
        date(2026, 3, 9),
        scope="training_data",
        reference_date=date(2026, 3, 20),
        policy=FreshnessPolicy(warn_after_days=7, fail_after_days=21),
    )

    assert check.status == "warning"
    assert check.age_days == 11


def test_assess_latest_week_freshness_reports_failed_for_missing_rows() -> None:
    check = assess_latest_week_freshness(
        None,
        scope="scoring_features",
        reference_date=date(2026, 3, 20),
        policy=FreshnessPolicy(warn_after_days=7, fail_after_days=21),
    )

    assert check.status == "failed"
    assert "no dated rows" in check.message.lower()
