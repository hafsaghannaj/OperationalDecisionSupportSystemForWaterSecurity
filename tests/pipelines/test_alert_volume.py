from libs.ml.alert_volume import assess_alert_volume


def test_assess_alert_volume_warns_when_current_rate_deviates_from_validation_baseline() -> None:
    status = assess_alert_volume(
        rows=10,
        medium_or_higher_alerts=6,
        high_alerts=3,
        validation_simulation={
            "medium_or_higher_alert": {"alert_rate": 0.3},
            "high_alert": {"alert_rate": 0.1},
        },
    )

    assert status.status == "warning"
    assert status.medium_or_higher_alert_rate == 0.6
    assert status.expected_medium_or_higher_alert_rate == 0.3
    assert status.high_alert_rate == 0.3


def test_assess_alert_volume_skips_without_validation_baseline() -> None:
    status = assess_alert_volume(
        rows=8,
        medium_or_higher_alerts=2,
        high_alerts=1,
        validation_simulation=None,
    )

    assert status.status == "skipped"
    assert "baseline" in status.message.lower()
