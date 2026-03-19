from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
from math import exp
from typing import Sequence

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from libs.ml.alert_volume import AlertVolumeStatus, assess_alert_volume
from libs.ml.artifacts import PromotedModel, load_model_version, load_promoted_model
from libs.ml.baselines import feature_vector
from libs.ml.drift import DriftStatus, assess_feature_drift
from libs.ml.freshness import (
    DEFAULT_SCORING_FRESHNESS_POLICY,
    FreshnessCheck,
    FreshnessPolicy,
    assess_latest_week_freshness,
    resolve_freshness_policy,
)
from libs.ml.thresholds import derive_severity, resolve_alert_thresholds
from services.api.app.db import SessionLocal
from services.api.app.db_models import AlertEventRecord, DistrictWeekFeature, ModelTrainingRun, RiskScore
from services.api.app.scoring_runs import persist_scoring_run


MODEL_VERSION = "heuristic-v1"


@dataclass(slots=True)
class ScoreComputation:
    score: float
    confidence: str
    severity: str
    driver_contributions: dict[str, float]
    driver_narrative: str
    recommended_action: str
    alert_status: str


@dataclass(slots=True)
class ScoreBatchResult:
    run_scope: str
    run_status: str
    model_version: str
    feature_build_version: str | None
    latest_week: str | None
    weeks_scored: int
    rows_scored: int
    rows_inserted: int
    rows_updated: int
    alerts_created_or_updated: int
    alerts_removed: int
    medium_or_higher_alerts: int
    high_alerts: int
    medium_or_higher_alert_rate: float | None
    high_alert_rate: float | None
    average_score: float | None
    max_score: float | None
    non_ok_quality_rows: int
    feature_freshness: FreshnessCheck
    feature_drift: DriftStatus
    alert_volume: AlertVolumeStatus

    def as_dict(self) -> dict[str, object]:
        return asdict(self)

    def summary(self) -> str:
        return (
            f"risk_scores[{self.model_version}]: {self.run_status}, scored {self.rows_scored} rows across "
            f"{self.weeks_scored} week(s), "
            f"inserted {self.rows_inserted}, updated {self.rows_updated}, "
            f"alerts upserted {self.alerts_created_or_updated}, alerts removed {self.alerts_removed}, "
            f"feature freshness {self.feature_freshness.status}, drift {self.feature_drift.status}, "
            f"alert volume {self.alert_volume.status}."
        )


def clamp(value: float, *, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def logistic(value: float) -> float:
    return 1 / (1 + exp(-value))


def rainfall_signal(feature: DistrictWeekFeature) -> float:
    anomaly = feature.rainfall_anomaly_zscore or 0.0
    return clamp(max(anomaly, 0.0) / 2.5)


def sanitation_gap(feature: DistrictWeekFeature) -> float:
    if feature.wash_access_basic_sanitation_pct is None:
        return 0.0
    return clamp((100.0 - feature.wash_access_basic_sanitation_pct) / 100.0)


def water_gap(feature: DistrictWeekFeature) -> float:
    if feature.wash_access_basic_water_pct is None:
        return 0.0
    return clamp((100.0 - feature.wash_access_basic_water_pct) / 100.0)


def recent_case_signal(feature: DistrictWeekFeature) -> float:
    if feature.lag_case_count_1w is None:
        return 0.0
    return clamp(feature.lag_case_count_1w / 25.0)


def rolling_case_signal(feature: DistrictWeekFeature) -> float:
    if feature.rolling_case_count_4w is None:
        return 0.0
    return clamp(feature.rolling_case_count_4w / 60.0)


def population_density_signal(feature: DistrictWeekFeature) -> float:
    if feature.population_density_km2 is None:
        return 0.0
    return clamp(feature.population_density_km2 / 5000.0)


def build_driver_contributions(feature: DistrictWeekFeature) -> dict[str, float]:
    contributions = {
        "Rainfall anomaly": round(0.28 * rainfall_signal(feature), 4),
        "Sanitation access gap": round(0.24 * sanitation_gap(feature), 4),
        "Recent case count": round(0.22 * recent_case_signal(feature), 4),
        "Four-week case pressure": round(0.14 * rolling_case_signal(feature), 4),
        "Water access gap": round(0.07 * water_gap(feature), 4),
        "Population density": round(0.05 * population_density_signal(feature), 4),
    }
    return {name: value for name, value in contributions.items() if value > 0}


def derive_confidence(feature: DistrictWeekFeature) -> str:
    if feature.quality_flag == "ok":
        return "high"
    if feature.quality_flag == "missing_static_and_weather":
        return "low"
    return "medium"


def recommended_action_for_severity(severity: str) -> tuple[str, str]:
    if severity == "high":
        return (
            "Trigger district review and field verification within 48 hours.",
            "open",
        )
    if severity == "medium":
        return (
            "Monitor closely and prepare targeted WASH messaging.",
            "open",
        )
    return (
        "Continue routine monitoring and review the next scheduled update.",
        "resolved",
    )


def build_driver_narrative(severity: str, contributions: dict[str, float]) -> str:
    if not contributions:
        return "Risk remains low because the current feature set shows limited pressure signals."

    top_drivers = [name for name, _value in sorted(contributions.items(), key=lambda item: item[1], reverse=True)[:3]]
    joined = ", ".join(top_drivers[:-1]) + f", and {top_drivers[-1]}" if len(top_drivers) > 1 else top_drivers[0]

    if severity == "high":
        return f"Risk is high this week due to strong pressure from {joined}."
    if severity == "medium":
        return f"Risk is elevated this week, driven primarily by {joined}."
    return f"Risk remains low, with only limited contribution from {joined}."


def heuristic_score(feature: DistrictWeekFeature) -> float:
    weighted_sum = sum(build_driver_contributions(feature).values())
    return round(clamp(logistic((weighted_sum - 0.35) * 4.2)), 4)


def predict_model_score(feature: DistrictWeekFeature, promoted_model: PromotedModel) -> float:
    probabilities = promoted_model.estimator.predict_proba(
        [feature_vector(feature, feature_columns=promoted_model.feature_columns)]
    )
    return round(clamp(float(probabilities[0][1])), 4)


def load_latest_registered_model(session: Session) -> PromotedModel | None:
    record = session.scalar(
        select(ModelTrainingRun)
        .where(ModelTrainingRun.registry_status.in_(("active", "challenger")))
        .order_by(desc(ModelTrainingRun.promoted_at), desc(ModelTrainingRun.trained_at))
        .limit(1)
    )
    if record is None:
        return None
    return load_model_version(record.model_version)


def resolve_scoring_model(session: Session, model_version: str | None = None) -> tuple[PromotedModel | None, str]:
    promoted_model = load_promoted_model()

    if model_version is None:
        if promoted_model is not None:
            return promoted_model, promoted_model.model_version
        latest_registered_model = load_latest_registered_model(session)
        if latest_registered_model is not None:
            return latest_registered_model, latest_registered_model.model_version
        return None, MODEL_VERSION

    if model_version == MODEL_VERSION:
        return None, MODEL_VERSION

    if promoted_model is not None and promoted_model.model_version == model_version:
        return promoted_model, promoted_model.model_version

    requested_model = load_model_version(model_version)
    if requested_model is not None:
        return requested_model, requested_model.model_version

    raise ValueError(f"Requested model_version '{model_version}' is not available.")


def resolve_feature_build_version(
    session: Session,
    *,
    promoted_model: PromotedModel | None = None,
    feature_build_version: str | None = None,
) -> str | None:
    if feature_build_version is not None:
        return feature_build_version

    if promoted_model is not None:
        promoted_feature_build_version = promoted_model.metadata.get("feature_build_version")
        if promoted_feature_build_version:
            return str(promoted_feature_build_version)

    return session.scalar(
        select(DistrictWeekFeature.feature_build_version)
        .order_by(DistrictWeekFeature.created_at.desc())
        .limit(1)
    )


def score_feature(
    feature: DistrictWeekFeature,
    *,
    promoted_model: PromotedModel | None = None,
) -> ScoreComputation:
    contributions = build_driver_contributions(feature)
    # Keep driver explanations stable while the model path graduates from heuristics to trained scoring.
    score = heuristic_score(feature) if promoted_model is None else predict_model_score(feature, promoted_model)
    confidence = derive_confidence(feature)
    thresholds = None if promoted_model is None else resolve_alert_thresholds(promoted_model.metadata.get("alert_thresholds"))
    severity = derive_severity(score, thresholds)
    recommended_action, alert_status = recommended_action_for_severity(severity)
    narrative = build_driver_narrative(severity, contributions)

    return ScoreComputation(
        score=score,
        confidence=confidence,
        severity=severity,
        driver_contributions=contributions,
        driver_narrative=narrative,
        recommended_action=recommended_action,
        alert_status=alert_status,
    )


def _score_query(latest_only: bool, *, feature_build_version: str | None):
    stmt = select(DistrictWeekFeature).order_by(DistrictWeekFeature.week_start_date, DistrictWeekFeature.region_id)
    if feature_build_version is not None:
        stmt = stmt.where(DistrictWeekFeature.feature_build_version == feature_build_version)
    if latest_only:
        latest_week = select(func.max(DistrictWeekFeature.week_start_date))
        if feature_build_version is not None:
            latest_week = latest_week.where(DistrictWeekFeature.feature_build_version == feature_build_version)
        latest_week = latest_week.scalar_subquery()
        stmt = stmt.where(DistrictWeekFeature.week_start_date == latest_week)
    return stmt


def assess_scoring_feature_drift(
    features: Sequence[DistrictWeekFeature],
    *,
    promoted_model: PromotedModel | None,
) -> DriftStatus:
    if promoted_model is None:
        return DriftStatus(
            scope="scoring_feature_drift",
            status="skipped",
            rows=len(features),
            compared_features=0,
            warning_features=0,
            failed_features=0,
            message="Drift check skipped because the heuristic fallback has no training feature profile.",
            top_drift_features=[],
        )

    return assess_feature_drift(
        promoted_model.metadata.get("training_feature_profile"),
        features,
        feature_columns=promoted_model.feature_columns,
        scope="scoring_feature_drift",
        policy=promoted_model.metadata.get("feature_drift_policy"),
    )


def load_scoring_feature_drift(
    session: Session,
    *,
    promoted_model: PromotedModel | None,
    feature_build_version: str | None = None,
    latest_only: bool = True,
) -> DriftStatus:
    resolved_feature_build_version = resolve_feature_build_version(
        session,
        promoted_model=promoted_model,
        feature_build_version=feature_build_version,
    )
    features = session.scalars(
        _score_query(
            latest_only,
            feature_build_version=resolved_feature_build_version,
        )
    ).all()
    return assess_scoring_feature_drift(features, promoted_model=promoted_model)


def assess_scoring_alert_volume(
    *,
    rows_scored: int,
    medium_or_higher_alerts: int,
    high_alerts: int,
    promoted_model: PromotedModel | None,
) -> AlertVolumeStatus:
    validation_simulation = None if promoted_model is None else promoted_model.metadata.get("alert_threshold_simulation")
    return assess_alert_volume(
        rows=rows_scored,
        medium_or_higher_alerts=medium_or_higher_alerts,
        high_alerts=high_alerts,
        validation_simulation=validation_simulation,
        scope="scoring_alert_volume",
    )


def aggregate_run_status(*statuses: str) -> str:
    relevant = [status for status in statuses if status != "skipped"]
    if not relevant:
        return "skipped"
    if "failed" in relevant:
        return "failed"
    if "warning" in relevant:
        return "warning"
    return "ok"


def _upsert_alert(session: Session, feature: DistrictWeekFeature, computation: ScoreComputation) -> tuple[int, int]:
    existing_alert = session.scalar(
        select(AlertEventRecord).where(
            AlertEventRecord.region_id == feature.region_id,
            AlertEventRecord.week_start_date == feature.week_start_date,
        )
    )

    if computation.severity == "low":
        if existing_alert is not None:
            session.delete(existing_alert)
            return (0, 1)
        return (0, 0)

    if existing_alert is None:
        session.add(
            AlertEventRecord(
                region_id=feature.region_id,
                week_start_date=feature.week_start_date,
                severity=computation.severity,
                recommended_action=computation.recommended_action,
                status=computation.alert_status,
            )
        )
        return (1, 0)

    existing_alert.severity = computation.severity
    existing_alert.recommended_action = computation.recommended_action
    existing_alert.status = computation.alert_status
    return (1, 0)


def _score_with_session(
    session: Session,
    *,
    latest_only: bool,
    model_version: str | None,
    feature_build_version: str | None,
    freshness_reference_date: date | None,
    freshness_policy: FreshnessPolicy | None,
) -> ScoreBatchResult:
    promoted_model, resolved_model_version = resolve_scoring_model(session, model_version)
    run_scope = "latest_week" if latest_only else "all_weeks"
    resolved_feature_build_version = resolve_feature_build_version(
        session,
        promoted_model=promoted_model,
        feature_build_version=feature_build_version,
    )
    features = session.scalars(
        _score_query(
            latest_only,
            feature_build_version=resolved_feature_build_version,
        )
    ).all()
    feature_freshness = assess_latest_week_freshness(
        max((feature.week_start_date for feature in features), default=None),
        scope="scoring_features",
        reference_date=freshness_reference_date,
        policy=resolve_freshness_policy(freshness_policy, default=DEFAULT_SCORING_FRESHNESS_POLICY),
    )
    if feature_freshness.status == "failed":
        raise ValueError(feature_freshness.message)
    feature_drift = assess_scoring_feature_drift(features, promoted_model=promoted_model)
    if feature_drift.status == "failed":
        raise ValueError(feature_drift.message)

    inserted = 0
    updated = 0
    alerts_upserted = 0
    alerts_removed = 0
    weeks_scored = len({feature.week_start_date for feature in features})
    latest_week = max((feature.week_start_date for feature in features), default=None)
    medium_or_higher_alerts = 0
    high_alerts = 0
    scores: list[float] = []
    non_ok_quality_rows = sum(1 for feature in features if feature.quality_flag != "ok")

    try:
        for feature in features:
            computation = score_feature(feature, promoted_model=promoted_model)
            scores.append(computation.score)
            if computation.severity in {"medium", "high"}:
                medium_or_higher_alerts += 1
            if computation.severity == "high":
                high_alerts += 1
            existing = session.scalar(
                select(RiskScore).where(
                    RiskScore.region_id == feature.region_id,
                    RiskScore.week_start_date == feature.week_start_date,
                )
            )

            payload = {
                "model_version": resolved_model_version,
                "score": computation.score,
                "confidence": computation.confidence,
                "driver_contributions": computation.driver_contributions,
                "driver_narrative": computation.driver_narrative,
            }

            if existing is None:
                session.add(
                    RiskScore(
                        region_id=feature.region_id,
                        week_start_date=feature.week_start_date,
                        **payload,
                    )
                )
                inserted += 1
            else:
                for key, value in payload.items():
                    setattr(existing, key, value)
                updated += 1

            created_or_updated, removed = _upsert_alert(session, feature, computation)
            alerts_upserted += created_or_updated
            alerts_removed += removed

        alert_volume = assess_scoring_alert_volume(
            rows_scored=len(features),
            medium_or_higher_alerts=medium_or_higher_alerts,
            high_alerts=high_alerts,
            promoted_model=promoted_model,
        )
        run_status = aggregate_run_status(
            feature_freshness.status,
            feature_drift.status,
            alert_volume.status,
        )
        persist_scoring_run(
            session,
            run_scope=run_scope,
            run_status=run_status,
            model_version=resolved_model_version,
            feature_build_version=resolved_feature_build_version,
            latest_week=latest_week,
            weeks_scored=weeks_scored,
            rows_scored=len(features),
            rows_inserted=inserted,
            rows_updated=updated,
            alerts_created_or_updated=alerts_upserted,
            alerts_removed=alerts_removed,
            medium_or_higher_alerts=medium_or_higher_alerts,
            high_alerts=high_alerts,
            medium_or_higher_alert_rate=None if not features else round(medium_or_higher_alerts / len(features), 4),
            high_alert_rate=None if not features else round(high_alerts / len(features), 4),
            average_score=None if not scores else round(sum(scores) / len(scores), 4),
            max_score=None if not scores else round(max(scores), 4),
            non_ok_quality_rows=non_ok_quality_rows,
            feature_freshness=feature_freshness.as_dict(),
            feature_drift=feature_drift.as_dict(),
            alert_volume=alert_volume.as_dict(),
        )
        session.commit()
    except Exception:
        session.rollback()
        raise

    return ScoreBatchResult(
        run_scope=run_scope,
        run_status=run_status,
        model_version=resolved_model_version,
        feature_build_version=resolved_feature_build_version,
        latest_week=None if latest_week is None else latest_week.isoformat(),
        weeks_scored=weeks_scored,
        rows_scored=len(features),
        rows_inserted=inserted,
        rows_updated=updated,
        alerts_created_or_updated=alerts_upserted,
        alerts_removed=alerts_removed,
        medium_or_higher_alerts=medium_or_higher_alerts,
        high_alerts=high_alerts,
        medium_or_higher_alert_rate=None if not features else round(medium_or_higher_alerts / len(features), 4),
        high_alert_rate=None if not features else round(high_alerts / len(features), 4),
        average_score=None if not scores else round(sum(scores) / len(scores), 4),
        max_score=None if not scores else round(max(scores), 4),
        non_ok_quality_rows=non_ok_quality_rows,
        feature_freshness=feature_freshness,
        feature_drift=feature_drift,
        alert_volume=alert_volume,
    )


def score_all_weeks(
    *,
    session: Session | None = None,
    model_version: str | None = None,
    feature_build_version: str | None = None,
    freshness_reference_date: date | None = None,
    freshness_policy: FreshnessPolicy | None = None,
) -> ScoreBatchResult:
    if session is not None:
        return _score_with_session(
            session,
            latest_only=False,
            model_version=model_version,
            feature_build_version=feature_build_version,
            freshness_reference_date=freshness_reference_date or date.today(),
            freshness_policy=freshness_policy,
        )

    with SessionLocal() as local_session:
        return _score_with_session(
            local_session,
            latest_only=False,
            model_version=model_version,
            feature_build_version=feature_build_version,
            freshness_reference_date=freshness_reference_date or date.today(),
            freshness_policy=freshness_policy,
        )


def score_latest_week(
    *,
    session: Session | None = None,
    model_version: str | None = None,
    feature_build_version: str | None = None,
    freshness_reference_date: date | None = None,
    freshness_policy: FreshnessPolicy | None = None,
) -> ScoreBatchResult:
    if session is not None:
        return _score_with_session(
            session,
            latest_only=True,
            model_version=model_version,
            feature_build_version=feature_build_version,
            freshness_reference_date=freshness_reference_date or date.today(),
            freshness_policy=freshness_policy,
        )

    with SessionLocal() as local_session:
        return _score_with_session(
            local_session,
            latest_only=True,
            model_version=model_version,
            feature_build_version=feature_build_version,
            freshness_reference_date=freshness_reference_date or date.today(),
            freshness_policy=freshness_policy,
        )
