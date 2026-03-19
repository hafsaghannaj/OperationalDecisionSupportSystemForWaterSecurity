from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
from typing import Literal


FreshnessState = Literal["ok", "warning", "failed", "skipped"]


@dataclass(slots=True)
class FreshnessPolicy:
    warn_after_days: int
    fail_after_days: int

    def as_dict(self) -> dict[str, int]:
        return asdict(self)


@dataclass(slots=True)
class FreshnessCheck:
    scope: str
    status: FreshnessState
    latest_week: str | None
    reference_date: str | None
    age_days: int | None
    warn_after_days: int
    fail_after_days: int
    message: str

    def as_dict(self) -> dict[str, str | int | None]:
        return asdict(self)


DEFAULT_TRAINING_FRESHNESS_POLICY = FreshnessPolicy(warn_after_days=28, fail_after_days=120)
DEFAULT_SCORING_FRESHNESS_POLICY = FreshnessPolicy(warn_after_days=14, fail_after_days=45)


def resolve_freshness_policy(
    policy: FreshnessPolicy | None,
    *,
    default: FreshnessPolicy,
) -> FreshnessPolicy:
    return policy if policy is not None else default


def assess_latest_week_freshness(
    latest_week: date | None,
    *,
    scope: str,
    reference_date: date | None,
    policy: FreshnessPolicy,
) -> FreshnessCheck:
    scope_label = scope.replace("_", " ")

    if reference_date is None:
        return FreshnessCheck(
            scope=scope,
            status="skipped",
            latest_week=None if latest_week is None else latest_week.isoformat(),
            reference_date=None,
            age_days=None,
            warn_after_days=policy.warn_after_days,
            fail_after_days=policy.fail_after_days,
            message=f"{scope_label.title()} freshness check skipped because no reference date was provided.",
        )

    if latest_week is None:
        return FreshnessCheck(
            scope=scope,
            status="failed",
            latest_week=None,
            reference_date=reference_date.isoformat(),
            age_days=None,
            warn_after_days=policy.warn_after_days,
            fail_after_days=policy.fail_after_days,
            message=f"{scope_label.title()} freshness check failed because no dated rows were available.",
        )

    age_days = max((reference_date - latest_week).days, 0)
    if age_days > policy.fail_after_days:
        status: FreshnessState = "failed"
        verdict = "exceeds the maximum allowed freshness lag"
    elif age_days > policy.warn_after_days:
        status = "warning"
        verdict = "is outside the preferred freshness window"
    else:
        status = "ok"
        verdict = "is within the allowed freshness window"

    return FreshnessCheck(
        scope=scope,
        status=status,
        latest_week=latest_week.isoformat(),
        reference_date=reference_date.isoformat(),
        age_days=age_days,
        warn_after_days=policy.warn_after_days,
        fail_after_days=policy.fail_after_days,
        message=(
            f"{scope_label.title()} freshness check {status}: latest week {latest_week.isoformat()} is {age_days} day(s) old "
            f"against reference date {reference_date.isoformat()} and {verdict}."
        ),
    )
