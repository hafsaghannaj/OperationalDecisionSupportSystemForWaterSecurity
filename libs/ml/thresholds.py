from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping, Sequence


DEFAULT_MEDIUM_THRESHOLD = 0.4
DEFAULT_HIGH_THRESHOLD = 0.7


def round_metric(value: float | None) -> float | None:
    if value is None:
        return None
    return round(float(value), 4)


@dataclass(slots=True)
class AlertThresholdPolicy:
    target_high_alert_rate: float = 0.15
    target_medium_alert_rate: float = 0.35
    min_high_precision: float = 0.5
    min_medium_precision: float = 0.35

    def as_dict(self) -> dict[str, float]:
        return asdict(self)


@dataclass(slots=True)
class ThresholdPerformance:
    threshold: float
    alerts: int
    true_positives: int
    alert_rate: float
    precision: float | None
    recall: float | None

    def as_dict(self) -> dict[str, float | int | None]:
        return asdict(self)


@dataclass(slots=True)
class AlertThresholdCalibration:
    medium: float
    high: float
    selection_status: str
    rows: int
    positive_rows: int
    medium_or_higher_alert: ThresholdPerformance
    high_alert: ThresholdPerformance
    medium_only_alert_rate: float

    def thresholds_as_dict(self) -> dict[str, float]:
        return {
            "medium": self.medium,
            "high": self.high,
        }

    def simulation_as_dict(self) -> dict[str, float | int | str | dict[str, float | int | None]]:
        return {
            "selection_status": self.selection_status,
            "rows": self.rows,
            "positive_rows": self.positive_rows,
            "medium_or_higher_alert": self.medium_or_higher_alert.as_dict(),
            "high_alert": self.high_alert.as_dict(),
            "medium_only_alert_rate": self.medium_only_alert_rate,
        }


DEFAULT_ALERT_THRESHOLDS = {
    "medium": DEFAULT_MEDIUM_THRESHOLD,
    "high": DEFAULT_HIGH_THRESHOLD,
}


def resolve_alert_thresholds(payload: Mapping[str, Any] | None = None) -> dict[str, float]:
    if not payload:
        return dict(DEFAULT_ALERT_THRESHOLDS)

    try:
        medium = round(float(payload.get("medium", DEFAULT_MEDIUM_THRESHOLD)), 4)
        high = round(float(payload.get("high", DEFAULT_HIGH_THRESHOLD)), 4)
    except (TypeError, ValueError):
        return dict(DEFAULT_ALERT_THRESHOLDS)

    if not (0.0 <= medium < high <= 1.0):
        return dict(DEFAULT_ALERT_THRESHOLDS)

    return {
        "medium": medium,
        "high": high,
    }


def derive_severity(score: float, thresholds: Mapping[str, Any] | None = None) -> str:
    resolved_thresholds = resolve_alert_thresholds(thresholds)
    if score >= resolved_thresholds["high"]:
        return "high"
    if score >= resolved_thresholds["medium"]:
        return "medium"
    return "low"


def threshold_candidates(scores: Sequence[float]) -> list[float]:
    return sorted(
        {
            0.0,
            1.0,
            DEFAULT_MEDIUM_THRESHOLD,
            DEFAULT_HIGH_THRESHOLD,
            *(round(max(0.0, min(1.0, float(score))), 4) for score in scores),
        }
    )


def evaluate_binary_threshold(scores: Sequence[float], labels: Sequence[int], threshold: float) -> ThresholdPerformance:
    alerts = [score >= threshold for score in scores]
    alert_count = sum(1 for alerted in alerts if alerted)
    true_positives = sum(1 for alerted, label in zip(alerts, labels, strict=True) if alerted and label == 1)
    positive_rows = sum(labels)
    precision = None if alert_count == 0 else round_metric(true_positives / alert_count)
    recall = None if positive_rows == 0 else round_metric(true_positives / positive_rows)

    return ThresholdPerformance(
        threshold=round(threshold, 4),
        alerts=alert_count,
        true_positives=true_positives,
        alert_rate=round_metric(alert_count / len(scores)) or 0.0,
        precision=precision,
        recall=recall,
    )


def choose_threshold(
    scores: Sequence[float],
    labels: Sequence[int],
    *,
    target_alert_rate: float,
    min_precision: float,
    max_threshold: float = 1.0,
) -> ThresholdPerformance:
    candidates = [
        evaluate_binary_threshold(scores, labels, threshold)
        for threshold in threshold_candidates(scores)
        if threshold < max_threshold
    ]
    active_candidates = [candidate for candidate in candidates if candidate.alerts > 0]
    if not active_candidates:
        return evaluate_binary_threshold(scores, labels, max_threshold)

    eligible = [
        candidate
        for candidate in active_candidates
        if candidate.alert_rate <= target_alert_rate and (candidate.precision or 0.0) >= min_precision
    ]
    if eligible:
        return max(
            eligible,
            key=lambda candidate: (
                candidate.recall or -1.0,
                candidate.precision or -1.0,
                candidate.alert_rate,
                candidate.threshold,
            ),
        )

    under_target = [candidate for candidate in active_candidates if candidate.alert_rate <= target_alert_rate]
    if under_target:
        return max(
            under_target,
            key=lambda candidate: (
                candidate.precision or -1.0,
                candidate.recall or -1.0,
                candidate.alert_rate,
                candidate.threshold,
            ),
        )

    return min(
        active_candidates,
        key=lambda candidate: (
            abs(candidate.alert_rate - target_alert_rate),
            -(candidate.precision or -1.0),
            -(candidate.recall or -1.0),
            candidate.threshold,
        ),
    )


def calibrate_alert_thresholds(
    scores: Sequence[float],
    labels: Sequence[int],
    *,
    policy: AlertThresholdPolicy | None = None,
) -> AlertThresholdCalibration:
    if not scores or len(scores) != len(labels):
        raise ValueError("Alert threshold calibration requires aligned score and label sequences.")

    resolved_policy = policy if policy is not None else AlertThresholdPolicy()
    high_alert = choose_threshold(
        scores,
        labels,
        target_alert_rate=resolved_policy.target_high_alert_rate,
        min_precision=resolved_policy.min_high_precision,
    )
    medium_or_higher_alert = choose_threshold(
        scores,
        labels,
        target_alert_rate=resolved_policy.target_medium_alert_rate,
        min_precision=resolved_policy.min_medium_precision,
        max_threshold=high_alert.threshold,
    )

    selection_status = "calibrated"
    thresholds = {
        "medium": medium_or_higher_alert.threshold,
        "high": high_alert.threshold,
    }
    if thresholds["medium"] >= thresholds["high"]:
        thresholds = dict(DEFAULT_ALERT_THRESHOLDS)
        selection_status = "fallback_default"
        medium_or_higher_alert = evaluate_binary_threshold(scores, labels, thresholds["medium"])
        high_alert = evaluate_binary_threshold(scores, labels, thresholds["high"])

    medium_only_alert_rate = round_metric(max(medium_or_higher_alert.alert_rate - high_alert.alert_rate, 0.0)) or 0.0
    return AlertThresholdCalibration(
        medium=thresholds["medium"],
        high=thresholds["high"],
        selection_status=selection_status,
        rows=len(scores),
        positive_rows=sum(labels),
        medium_or_higher_alert=medium_or_higher_alert,
        high_alert=high_alert,
        medium_only_alert_rate=medium_only_alert_rate,
    )
