from __future__ import annotations

import json
from datetime import date

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from libs.schemas.risk import AlertEvent, DriverBreakdown, RegionSummary, RiskHistoryPoint, RiskSnapshot
from services.api.app.db_models import AdminBoundary, AlertEventRecord, RiskScore
from services.api.app.time import format_week_string, parse_week_string


def derive_risk_level(score: float | None) -> str:
    if score is None:
        return "low"
    if score >= 0.7:
        return "high"
    if score >= 0.4:
        return "medium"
    return "low"


def top_driver_names(driver_contributions: dict[str, float] | None, limit: int = 3) -> list[str]:
    if not driver_contributions:
        return []
    ranked = sorted(driver_contributions.items(), key=lambda item: abs(item[1]), reverse=True)
    return [name for name, _value in ranked[:limit]]


def latest_week_query() -> Select[tuple[date | None]]:
    return select(func.max(RiskScore.week_start_date))


def list_regions(session: Session) -> list[RegionSummary]:
    latest_week = session.scalar(latest_week_query())

    if latest_week is None:
        stmt = select(AdminBoundary.region_id, AdminBoundary.name).order_by(AdminBoundary.name)
        return [
            RegionSummary(region_id=row.region_id, name=row.name, risk_level="low")
            for row in session.execute(stmt)
        ]

    latest_scores = (
        select(RiskScore.region_id.label("region_id"), RiskScore.score.label("score"))
        .where(RiskScore.week_start_date == latest_week)
        .subquery()
    )

    stmt = (
        select(AdminBoundary.region_id, AdminBoundary.name, latest_scores.c.score)
        .outerjoin(latest_scores, latest_scores.c.region_id == AdminBoundary.region_id)
        .order_by(AdminBoundary.name)
    )

    return [
        RegionSummary(
            region_id=row.region_id,
            name=row.name,
            risk_level=derive_risk_level(row.score),
        )
        for row in session.execute(stmt)
    ]


def list_latest_risk(session: Session) -> list[RiskSnapshot]:
    latest_week = session.scalar(latest_week_query())
    if latest_week is None:
        return []

    stmt = select(RiskScore).where(RiskScore.week_start_date == latest_week).order_by(RiskScore.score.desc())
    scores = session.scalars(stmt).all()

    return [
        RiskSnapshot(
            region_id=score.region_id,
            week=format_week_string(score.week_start_date),
            score=score.score,
            confidence=score.confidence,
            top_drivers=top_driver_names(score.driver_contributions),
        )
        for score in scores
    ]


def get_risk_history(session: Session, region_id: str) -> list[RiskHistoryPoint]:
    stmt = (
        select(RiskScore.week_start_date, RiskScore.score)
        .where(RiskScore.region_id == region_id)
        .order_by(RiskScore.week_start_date)
    )

    rows = session.execute(stmt).all()
    return [RiskHistoryPoint(week=format_week_string(row.week_start_date), score=row.score) for row in rows]


def get_driver_breakdown(session: Session, region_id: str, week: str) -> DriverBreakdown | None:
    week_start_date = parse_week_string(week)
    stmt = select(RiskScore).where(
        RiskScore.region_id == region_id,
        RiskScore.week_start_date == week_start_date,
    )
    score = session.scalar(stmt)
    if score is None:
        return None

    return DriverBreakdown(
        region_id=region_id,
        week=week,
        drivers=score.driver_contributions or {},
        narrative=score.driver_narrative or "No driver narrative has been recorded yet.",
    )


def list_alerts(session: Session) -> list[AlertEvent]:
    severity_order = {
        "high": 0,
        "medium": 1,
        "low": 2,
    }

    alerts = session.scalars(
        select(AlertEventRecord)
        .where(AlertEventRecord.status != "resolved")
        .order_by(AlertEventRecord.week_start_date.desc())
    ).all()
    alerts.sort(key=lambda alert: (severity_order.get(alert.severity, 99), alert.region_id))

    return [
        AlertEvent(
            region_id=alert.region_id,
            week=format_week_string(alert.week_start_date),
            severity=alert.severity,
            recommended_action=alert.recommended_action,
        )
        for alert in alerts
    ]


def get_regions_geojson(session: Session) -> dict:
    """Return a GeoJSON FeatureCollection of all district boundaries with latest risk scores."""
    latest_week = session.scalar(latest_week_query())

    latest_scores: dict[str, float] = {}
    if latest_week is not None:
        rows = session.execute(
            select(RiskScore.region_id, RiskScore.score).where(RiskScore.week_start_date == latest_week)
        ).all()
        latest_scores = {row.region_id: row.score for row in rows}

    from sqlalchemy import text as sa_text
    geom_rows = session.execute(
        sa_text(
            "SELECT region_id, name, ST_AsGeoJSON(geom)::text AS geojson "
            "FROM admin_boundaries WHERE geom IS NOT NULL"
        )
    ).all()

    features = []
    for row in geom_rows:
        score = latest_scores.get(row.region_id)
        features.append({
            "type": "Feature",
            "geometry": json.loads(row.geojson),
            "properties": {
                "region_id": row.region_id,
                "name": row.name,
                "score": score,
                "risk_level": derive_risk_level(score),
            },
        })

    return {"type": "FeatureCollection", "features": features}


def resolve_alert(session: Session, region_id: str, week: str) -> bool:
    """Mark an alert as resolved. Returns True if found and updated, False if not found."""
    week_start_date = parse_week_string(week)
    alert = session.scalar(
        select(AlertEventRecord).where(
            AlertEventRecord.region_id == region_id,
            AlertEventRecord.week_start_date == week_start_date,
        )
    )
    if alert is None:
        return False
    alert.status = "resolved"
    session.commit()
    return True


def list_all_risk(session: Session) -> list[dict]:
    """Return risk scores for all regions across all weeks (for time slider)."""
    stmt = (
        select(RiskScore.region_id, RiskScore.week_start_date, RiskScore.score, RiskScore.confidence)
        .order_by(RiskScore.week_start_date, RiskScore.region_id)
    )
    rows = session.execute(stmt).all()
    return [
        {
            "region_id": row.region_id,
            "week": format_week_string(row.week_start_date),
            "score": row.score,
            "confidence": row.confidence,
        }
        for row in rows
    ]


def list_data_quality(session: Session) -> list[dict]:
    """Return data quality flags per district-week."""
    from services.api.app.db_models import DistrictWeekFeature
    stmt = (
        select(
            DistrictWeekFeature.region_id,
            DistrictWeekFeature.week_start_date,
            DistrictWeekFeature.quality_flag,
            DistrictWeekFeature.rainfall_total_mm_7d,
            DistrictWeekFeature.feature_build_version,
        )
        .order_by(DistrictWeekFeature.week_start_date, DistrictWeekFeature.region_id)
    )
    rows = session.execute(stmt).all()
    return [
        {
            "region_id": row.region_id,
            "week": format_week_string(row.week_start_date),
            "quality_flag": row.quality_flag,
            "rainfall_total_mm_7d": row.rainfall_total_mm_7d,
            "confidence": "high" if row.quality_flag == "ok" else ("low" if "and" in row.quality_flag else "medium"),
        }
        for row in rows
    ]
