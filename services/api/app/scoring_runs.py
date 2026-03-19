from __future__ import annotations

from datetime import date
from typing import Any, Mapping

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from libs.schemas.risk import (
    AlertVolumeStatus,
    DriftStatus,
    FeatureDriftDetail,
    FreshnessStatus,
    ScoringHealth,
    ScoringRunSummary,
)
from services.api.app.db_models import ScoringRunRecord


def build_freshness_status(payload: Mapping[str, Any] | None) -> FreshnessStatus:
    payload = payload or {}
    return FreshnessStatus(
        scope=str(payload.get("scope", "unknown")),
        status=str(payload.get("status", "skipped")),
        latest_week=payload.get("latest_week"),
        reference_date=payload.get("reference_date"),
        age_days=payload.get("age_days"),
        warn_after_days=int(payload.get("warn_after_days", 0)),
        fail_after_days=int(payload.get("fail_after_days", 0)),
        message=str(payload.get("message", "Freshness metadata not recorded.")),
    )


def build_feature_drift_detail(payload: Mapping[str, Any]) -> FeatureDriftDetail:
    return FeatureDriftDetail(
        feature=str(payload.get("feature", "unknown")),
        status=str(payload.get("status", "skipped")),
        training_mean=payload.get("training_mean"),
        current_mean=payload.get("current_mean"),
        shift_score=payload.get("shift_score"),
        missing_rate_delta=float(payload.get("missing_rate_delta", 0.0)),
        message=str(payload.get("message", "Feature drift detail not recorded.")),
    )


def build_drift_status(payload: Mapping[str, Any] | None) -> DriftStatus:
    payload = payload or {}
    return DriftStatus(
        scope=str(payload.get("scope", "unknown")),
        status=str(payload.get("status", "skipped")),
        rows=int(payload.get("rows", 0)),
        compared_features=int(payload.get("compared_features", 0)),
        warning_features=int(payload.get("warning_features", 0)),
        failed_features=int(payload.get("failed_features", 0)),
        message=str(payload.get("message", "Drift metadata not recorded.")),
        top_drift_features=[build_feature_drift_detail(detail) for detail in payload.get("top_drift_features", [])],
    )


def build_alert_volume_status(payload: Mapping[str, Any] | None) -> AlertVolumeStatus:
    payload = payload or {}
    return AlertVolumeStatus(
        scope=str(payload.get("scope", "unknown")),
        status=str(payload.get("status", "skipped")),
        rows=int(payload.get("rows", 0)),
        medium_or_higher_alerts=int(payload.get("medium_or_higher_alerts", 0)),
        high_alerts=int(payload.get("high_alerts", 0)),
        medium_or_higher_alert_rate=payload.get("medium_or_higher_alert_rate"),
        high_alert_rate=payload.get("high_alert_rate"),
        expected_medium_or_higher_alert_rate=payload.get("expected_medium_or_higher_alert_rate"),
        expected_high_alert_rate=payload.get("expected_high_alert_rate"),
        medium_or_higher_rate_delta=payload.get("medium_or_higher_rate_delta"),
        high_alert_rate_delta=payload.get("high_alert_rate_delta"),
        warn_rate_delta=float(payload.get("warn_rate_delta", 0.0)),
        fail_rate_delta=float(payload.get("fail_rate_delta", 0.0)),
        message=str(payload.get("message", "Alert-volume metadata not recorded.")),
    )


def build_scoring_run_summary(record: ScoringRunRecord) -> ScoringRunSummary:
    return ScoringRunSummary(
        run_scope=record.run_scope,
        run_status=record.run_status,
        executed_at=record.executed_at.isoformat(),
        model_version=record.model_version,
        feature_build_version=record.feature_build_version,
        latest_week=None if record.latest_week_start_date is None else record.latest_week_start_date.isoformat(),
        weeks_scored=record.weeks_scored,
        rows_scored=record.rows_scored,
        rows_inserted=record.rows_inserted,
        rows_updated=record.rows_updated,
        alerts_created_or_updated=record.alerts_created_or_updated,
        alerts_removed=record.alerts_removed,
        medium_or_higher_alerts=record.medium_or_higher_alerts,
        high_alerts=record.high_alerts,
        medium_or_higher_alert_rate=record.medium_or_higher_alert_rate,
        high_alert_rate=record.high_alert_rate,
        average_score=record.average_score,
        max_score=record.max_score,
        non_ok_quality_rows=record.non_ok_quality_rows,
        feature_freshness=build_freshness_status(record.feature_freshness),
        feature_drift=build_drift_status(record.feature_drift),
        alert_volume=build_alert_volume_status(record.alert_volume),
    )


def load_scoring_health(session: Session, *, recent_limit: int = 5) -> ScoringHealth:
    recent_runs = session.scalars(
        select(ScoringRunRecord)
        .order_by(desc(ScoringRunRecord.executed_at))
        .limit(recent_limit)
    ).all()
    latest_run = recent_runs[0] if recent_runs else None
    return ScoringHealth(
        latest_run=None if latest_run is None else build_scoring_run_summary(latest_run),
        recent_runs=[build_scoring_run_summary(run) for run in recent_runs],
    )


def persist_scoring_run(
    session: Session,
    *,
    run_scope: str,
    run_status: str,
    model_version: str,
    feature_build_version: str | None,
    latest_week: date | None,
    weeks_scored: int,
    rows_scored: int,
    rows_inserted: int,
    rows_updated: int,
    alerts_created_or_updated: int,
    alerts_removed: int,
    medium_or_higher_alerts: int,
    high_alerts: int,
    medium_or_higher_alert_rate: float | None,
    high_alert_rate: float | None,
    average_score: float | None,
    max_score: float | None,
    non_ok_quality_rows: int,
    feature_freshness: Mapping[str, Any],
    feature_drift: Mapping[str, Any],
    alert_volume: Mapping[str, Any],
) -> ScoringRunRecord:
    record = ScoringRunRecord(
        run_scope=run_scope,
        run_status=run_status,
        model_version=model_version,
        feature_build_version=feature_build_version,
        latest_week_start_date=latest_week,
        weeks_scored=weeks_scored,
        rows_scored=rows_scored,
        rows_inserted=rows_inserted,
        rows_updated=rows_updated,
        alerts_created_or_updated=alerts_created_or_updated,
        alerts_removed=alerts_removed,
        medium_or_higher_alerts=medium_or_higher_alerts,
        high_alerts=high_alerts,
        medium_or_higher_alert_rate=medium_or_higher_alert_rate,
        high_alert_rate=high_alert_rate,
        average_score=average_score,
        max_score=max_score,
        non_ok_quality_rows=non_ok_quality_rows,
        feature_freshness=dict(feature_freshness),
        feature_drift=dict(feature_drift),
        alert_volume=dict(alert_volume),
    )
    session.add(record)
    session.flush()
    return record
