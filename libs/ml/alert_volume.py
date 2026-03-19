from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Literal, Mapping


AlertVolumeState = Literal["ok", "warning", "failed", "skipped"]


def round_metric(value: float | None) -> float | None:
    if value is None:
        return None
    return round(float(value), 4)


@dataclass(slots=True)
class AlertVolumePolicy:
    warn_rate_delta: float = 0.15
    fail_rate_delta: float = 0.3
    min_rows: int = 3

    def as_dict(self) -> dict[str, float | int]:
        return asdict(self)


@dataclass(slots=True)
class AlertVolumeStatus:
    scope: str
    status: AlertVolumeState
    rows: int
    medium_or_higher_alerts: int
    high_alerts: int
    medium_or_higher_alert_rate: float | None
    high_alert_rate: float | None
    expected_medium_or_higher_alert_rate: float | None
    expected_high_alert_rate: float | None
    medium_or_higher_rate_delta: float | None
    high_alert_rate_delta: float | None
    warn_rate_delta: float
    fail_rate_delta: float
    message: str

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


DEFAULT_ALERT_VOLUME_POLICY = AlertVolumePolicy()


def resolve_alert_volume_policy(
    policy: AlertVolumePolicy | Mapping[str, Any] | None,
    *,
    default: AlertVolumePolicy | None = None,
) -> AlertVolumePolicy:
    resolved_default = default if default is not None else DEFAULT_ALERT_VOLUME_POLICY
    if policy is None:
        return resolved_default
    if isinstance(policy, AlertVolumePolicy):
        return policy

    try:
        return AlertVolumePolicy(
            warn_rate_delta=float(policy.get("warn_rate_delta", resolved_default.warn_rate_delta)),
            fail_rate_delta=float(policy.get("fail_rate_delta", resolved_default.fail_rate_delta)),
            min_rows=int(policy.get("min_rows", resolved_default.min_rows)),
        )
    except (TypeError, ValueError):
        return resolved_default


def extract_expected_alert_rates(simulation: Mapping[str, Any] | None) -> tuple[float | None, float | None]:
    if not simulation:
        return (None, None)

    medium_alert = simulation.get("medium_or_higher_alert") or {}
    high_alert = simulation.get("high_alert") or {}
    medium_rate = medium_alert.get("alert_rate")
    high_rate = high_alert.get("alert_rate")
    return (
        None if medium_rate is None else float(medium_rate),
        None if high_rate is None else float(high_rate),
    )


def skipped_alert_volume_status(
    scope: str,
    *,
    rows: int,
    medium_or_higher_alerts: int,
    high_alerts: int,
    message: str,
    policy: AlertVolumePolicy,
) -> AlertVolumeStatus:
    medium_rate = None if rows <= 0 else round_metric(medium_or_higher_alerts / rows)
    high_rate = None if rows <= 0 else round_metric(high_alerts / rows)
    return AlertVolumeStatus(
        scope=scope,
        status="skipped",
        rows=rows,
        medium_or_higher_alerts=medium_or_higher_alerts,
        high_alerts=high_alerts,
        medium_or_higher_alert_rate=medium_rate,
        high_alert_rate=high_rate,
        expected_medium_or_higher_alert_rate=None,
        expected_high_alert_rate=None,
        medium_or_higher_rate_delta=None,
        high_alert_rate_delta=None,
        warn_rate_delta=policy.warn_rate_delta,
        fail_rate_delta=policy.fail_rate_delta,
        message=message,
    )


def assess_alert_volume(
    *,
    rows: int,
    medium_or_higher_alerts: int,
    high_alerts: int,
    validation_simulation: Mapping[str, Any] | None,
    policy: AlertVolumePolicy | Mapping[str, Any] | None = None,
    scope: str = "scoring_alert_volume",
) -> AlertVolumeStatus:
    resolved_policy = resolve_alert_volume_policy(policy)
    medium_rate = None if rows <= 0 else round_metric(medium_or_higher_alerts / rows)
    high_rate = None if rows <= 0 else round_metric(high_alerts / rows)

    if rows < resolved_policy.min_rows:
        return skipped_alert_volume_status(
            scope,
            rows=rows,
            medium_or_higher_alerts=medium_or_higher_alerts,
            high_alerts=high_alerts,
            message=(
                f"Alert-volume check skipped because only {rows} row(s) were scored; "
                f"need at least {resolved_policy.min_rows}."
            ),
            policy=resolved_policy,
        )

    expected_medium_rate, expected_high_rate = extract_expected_alert_rates(validation_simulation)
    if expected_medium_rate is None or expected_high_rate is None:
        return skipped_alert_volume_status(
            scope,
            rows=rows,
            medium_or_higher_alerts=medium_or_higher_alerts,
            high_alerts=high_alerts,
            message="Alert-volume check skipped because no validation alert-rate baseline was available.",
            policy=resolved_policy,
        )

    medium_delta = round_metric(abs((medium_rate or 0.0) - expected_medium_rate))
    high_delta = round_metric(abs((high_rate or 0.0) - expected_high_rate))

    reasons: list[str] = []
    if (medium_delta or 0.0) > resolved_policy.fail_rate_delta or (high_delta or 0.0) > resolved_policy.fail_rate_delta:
        status: AlertVolumeState = "failed"
        reasons.append("observed alert volume is materially outside the validation baseline")
    elif (medium_delta or 0.0) > resolved_policy.warn_rate_delta or (high_delta or 0.0) > resolved_policy.warn_rate_delta:
        status = "warning"
        reasons.append("observed alert volume is drifting away from the validation baseline")
    else:
        status = "ok"
        reasons.append("observed alert volume is within the expected validation range")

    return AlertVolumeStatus(
        scope=scope,
        status=status,
        rows=rows,
        medium_or_higher_alerts=medium_or_higher_alerts,
        high_alerts=high_alerts,
        medium_or_higher_alert_rate=medium_rate,
        high_alert_rate=high_rate,
        expected_medium_or_higher_alert_rate=round_metric(expected_medium_rate),
        expected_high_alert_rate=round_metric(expected_high_rate),
        medium_or_higher_rate_delta=medium_delta,
        high_alert_rate_delta=high_delta,
        warn_rate_delta=resolved_policy.warn_rate_delta,
        fail_rate_delta=resolved_policy.fail_rate_delta,
        message=(
            f"Alert-volume check {status}: medium+ rate {medium_rate} vs expected {round_metric(expected_medium_rate)}, "
            f"high rate {high_rate} vs expected {round_metric(expected_high_rate)}; {'; '.join(reasons)}."
        ),
    )
