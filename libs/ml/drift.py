from __future__ import annotations

from dataclasses import asdict, dataclass
from statistics import mean, pstdev
from typing import Any, Literal, Mapping, Sequence

from libs.ml.baselines import MODEL_FEATURE_COLUMNS


DriftState = Literal["ok", "warning", "failed", "skipped"]


def round_metric(value: float | None) -> float | None:
    if value is None:
        return None
    return round(float(value), 4)


@dataclass(slots=True)
class DriftPolicy:
    warn_shift_score: float = 1.0
    fail_shift_score: float = 2.0
    warn_missing_rate_delta: float = 0.15
    fail_missing_rate_delta: float = 0.3
    min_rows: int = 3
    max_reported_features: int = 3

    def as_dict(self) -> dict[str, float | int]:
        return asdict(self)


@dataclass(slots=True)
class FeatureDriftDetail:
    feature: str
    status: DriftState
    training_mean: float | None
    current_mean: float | None
    shift_score: float | None
    missing_rate_delta: float
    message: str

    def as_dict(self) -> dict[str, str | float | None]:
        return asdict(self)


@dataclass(slots=True)
class DriftStatus:
    scope: str
    status: DriftState
    rows: int
    compared_features: int
    warning_features: int
    failed_features: int
    message: str
    top_drift_features: list[FeatureDriftDetail]

    def as_dict(self) -> dict[str, object]:
        return {
            "scope": self.scope,
            "status": self.status,
            "rows": self.rows,
            "compared_features": self.compared_features,
            "warning_features": self.warning_features,
            "failed_features": self.failed_features,
            "message": self.message,
            "top_drift_features": [detail.as_dict() for detail in self.top_drift_features],
        }


DEFAULT_FEATURE_DRIFT_POLICY = DriftPolicy()


def resolve_drift_policy(
    policy: DriftPolicy | Mapping[str, Any] | None,
    *,
    default: DriftPolicy | None = None,
) -> DriftPolicy:
    resolved_default = default if default is not None else DEFAULT_FEATURE_DRIFT_POLICY
    if policy is None:
        return resolved_default
    if isinstance(policy, DriftPolicy):
        return policy

    try:
        return DriftPolicy(
            warn_shift_score=float(policy.get("warn_shift_score", resolved_default.warn_shift_score)),
            fail_shift_score=float(policy.get("fail_shift_score", resolved_default.fail_shift_score)),
            warn_missing_rate_delta=float(
                policy.get("warn_missing_rate_delta", resolved_default.warn_missing_rate_delta)
            ),
            fail_missing_rate_delta=float(
                policy.get("fail_missing_rate_delta", resolved_default.fail_missing_rate_delta)
            ),
            min_rows=int(policy.get("min_rows", resolved_default.min_rows)),
            max_reported_features=int(policy.get("max_reported_features", resolved_default.max_reported_features)),
        )
    except (TypeError, ValueError):
        return resolved_default


def feature_values(rows: Sequence[Any], feature: str) -> list[float]:
    values: list[float] = []
    for row in rows:
        value = getattr(row, feature, None)
        if value is None:
            continue
        values.append(float(value))
    return values


def build_feature_profile(
    rows: Sequence[Any],
    *,
    feature_columns: Sequence[str] = MODEL_FEATURE_COLUMNS,
) -> dict[str, dict[str, float | int | None]]:
    row_count = len(rows)
    profile: dict[str, dict[str, float | int | None]] = {}
    for feature in feature_columns:
        values = feature_values(rows, feature)
        non_null_rows = len(values)
        profile[feature] = {
            "rows": row_count,
            "non_null_rows": non_null_rows,
            "mean": round_metric(mean(values)) if values else None,
            "std": round_metric(pstdev(values)) if len(values) > 1 else (0.0 if values else None),
            "missing_rate": round_metric((row_count - non_null_rows) / row_count) if row_count else None,
        }
    return profile


def skip_drift_status(scope: str, *, rows: int, message: str) -> DriftStatus:
    return DriftStatus(
        scope=scope,
        status="skipped",
        rows=rows,
        compared_features=0,
        warning_features=0,
        failed_features=0,
        message=message,
        top_drift_features=[],
    )


def normalized_shift_score(
    training_mean: float | None,
    current_mean: float | None,
    training_std: float | None,
) -> float | None:
    if training_mean is None or current_mean is None:
        return None

    scale = max(abs(training_mean) * 0.1, training_std or 0.0, 1.0)
    return round_metric(abs(current_mean - training_mean) / scale)


def compare_feature_profile(
    feature: str,
    training_profile: Mapping[str, Any],
    current_profile: Mapping[str, Any],
    *,
    policy: DriftPolicy,
) -> FeatureDriftDetail:
    training_mean = training_profile.get("mean")
    current_mean = current_profile.get("mean")
    shift_score = normalized_shift_score(training_mean, current_mean, training_profile.get("std"))
    training_missing_rate = float(training_profile.get("missing_rate") or 0.0)
    current_missing_rate = float(current_profile.get("missing_rate") or 0.0)
    missing_rate_delta = round_metric(abs(current_missing_rate - training_missing_rate)) or 0.0

    reasons: list[str] = []
    status: DriftState = "ok"
    if shift_score is not None:
        if shift_score > policy.fail_shift_score:
            status = "failed"
            reasons.append(f"shift score {shift_score:.2f} exceeds fail threshold {policy.fail_shift_score:.2f}")
        elif shift_score > policy.warn_shift_score:
            status = "warning"
            reasons.append(f"shift score {shift_score:.2f} exceeds warning threshold {policy.warn_shift_score:.2f}")

    if missing_rate_delta > policy.fail_missing_rate_delta:
        status = "failed"
        reasons.append(
            f"missing-rate delta {missing_rate_delta:.2f} exceeds fail threshold {policy.fail_missing_rate_delta:.2f}"
        )
    elif missing_rate_delta > policy.warn_missing_rate_delta and status != "failed":
        status = "warning"
        reasons.append(
            f"missing-rate delta {missing_rate_delta:.2f} exceeds warning threshold {policy.warn_missing_rate_delta:.2f}"
        )

    if not reasons:
        reasons.append("distribution remains within the expected training range")

    return FeatureDriftDetail(
        feature=feature,
        status=status,
        training_mean=round_metric(float(training_mean)) if training_mean is not None else None,
        current_mean=round_metric(float(current_mean)) if current_mean is not None else None,
        shift_score=shift_score,
        missing_rate_delta=missing_rate_delta,
        message=f"{feature}: {'; '.join(reasons)}.",
    )


def detail_sort_key(detail: FeatureDriftDetail) -> tuple[int, float, float]:
    severity_rank = {
        "failed": 2,
        "warning": 1,
        "ok": 0,
        "skipped": -1,
    }
    return (
        severity_rank.get(detail.status, -1),
        detail.shift_score or 0.0,
        detail.missing_rate_delta,
    )


def assess_feature_drift(
    training_feature_profile: Mapping[str, Mapping[str, Any]] | None,
    current_rows: Sequence[Any],
    *,
    feature_columns: Sequence[str] = MODEL_FEATURE_COLUMNS,
    scope: str = "scoring_feature_drift",
    policy: DriftPolicy | Mapping[str, Any] | None = None,
) -> DriftStatus:
    resolved_policy = resolve_drift_policy(policy)
    row_count = len(current_rows)

    if not training_feature_profile:
        return skip_drift_status(
            scope,
            rows=row_count,
            message="Drift check skipped because no training feature profile was available.",
        )

    if row_count < resolved_policy.min_rows:
        return skip_drift_status(
            scope,
            rows=row_count,
            message=f"Drift check skipped because only {row_count} row(s) were available; need at least {resolved_policy.min_rows}.",
        )

    current_profile = build_feature_profile(current_rows, feature_columns=feature_columns)
    details = [
        compare_feature_profile(
            feature,
            training_feature_profile.get(feature) or {},
            current_profile.get(feature) or {},
            policy=resolved_policy,
        )
        for feature in feature_columns
        if feature in training_feature_profile
    ]

    if not details:
        return skip_drift_status(
            scope,
            rows=row_count,
            message="Drift check skipped because no shared features were available for comparison.",
        )

    failed_features = sum(1 for detail in details if detail.status == "failed")
    warning_features = sum(1 for detail in details if detail.status == "warning")
    if failed_features:
        status: DriftState = "failed"
        message = f"Feature drift check failed for {failed_features} feature(s); latest window is outside the training envelope."
    elif warning_features:
        status = "warning"
        message = f"Feature drift check warned on {warning_features} feature(s); latest window is shifting away from training."
    else:
        status = "ok"
        message = f"No material feature drift detected across {len(details)} feature(s)."

    ranked_details = sorted(details, key=detail_sort_key, reverse=True)[: resolved_policy.max_reported_features]
    return DriftStatus(
        scope=scope,
        status=status,
        rows=row_count,
        compared_features=len(details),
        warning_features=warning_features,
        failed_features=failed_features,
        message=message,
        top_drift_features=ranked_details,
    )
