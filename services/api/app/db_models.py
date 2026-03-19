from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any
from uuid import uuid4

from geoalchemy2 import Geometry
from sqlalchemy import JSON, Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from services.api.app.db import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def default_id() -> str:
    return str(uuid4())


class SourceRun(Base):
    __tablename__ = "source_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=default_id)
    source_name: Mapped[str] = mapped_column(String(120), index=True)
    upstream_asset_uri: Mapped[str | None] = mapped_column(Text, nullable=True)
    checksum: Mapped[str | None] = mapped_column(String(255), nullable=True)
    record_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="success")
    executed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class AdminBoundary(Base):
    __tablename__ = "admin_boundaries"

    region_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    country_code: Mapped[str] = mapped_column(String(8), index=True)
    admin_level: Mapped[int] = mapped_column(Integer)
    source_run_id: Mapped[str | None] = mapped_column(ForeignKey("source_runs.id", ondelete="SET NULL"), nullable=True)
    geom: Mapped[Any | None] = mapped_column(Geometry("MULTIPOLYGON", srid=4326, spatial_index=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class DistrictWeekFeature(Base):
    __tablename__ = "district_week_features"
    __table_args__ = (
        UniqueConstraint("region_id", "week_start_date", "feature_build_version", name="uq_features_region_week_build"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=default_id)
    region_id: Mapped[str] = mapped_column(ForeignKey("admin_boundaries.region_id", ondelete="CASCADE"), index=True)
    week_start_date: Mapped[date] = mapped_column(Date, index=True)
    country_code: Mapped[str] = mapped_column(String(8))
    admin_level: Mapped[int] = mapped_column(Integer)
    source_run_id: Mapped[str | None] = mapped_column(ForeignKey("source_runs.id", ondelete="SET NULL"), nullable=True)
    feature_build_version: Mapped[str] = mapped_column(String(50))
    quality_flag: Mapped[str] = mapped_column(String(32), default="ok")
    rainfall_total_mm_7d: Mapped[float | None] = mapped_column(Float, nullable=True)
    rainfall_anomaly_zscore: Mapped[float | None] = mapped_column(Float, nullable=True)
    population_total: Mapped[float | None] = mapped_column(Float, nullable=True)
    population_density_km2: Mapped[float | None] = mapped_column(Float, nullable=True)
    wash_access_basic_water_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    wash_access_basic_sanitation_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    lag_case_count_1w: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rolling_case_count_4w: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class DistrictWeekLabel(Base):
    __tablename__ = "district_week_labels"
    __table_args__ = (
        UniqueConstraint("region_id", "week_start_date", "label_source", name="uq_labels_region_week_source"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=default_id)
    region_id: Mapped[str] = mapped_column(ForeignKey("admin_boundaries.region_id", ondelete="CASCADE"), index=True)
    week_start_date: Mapped[date] = mapped_column(Date, index=True)
    label_event: Mapped[bool] = mapped_column(Boolean)
    case_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    label_source: Mapped[str] = mapped_column(String(120))
    label_observed_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    source_run_id: Mapped[str | None] = mapped_column(ForeignKey("source_runs.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class RiskScore(Base):
    __tablename__ = "risk_scores"
    __table_args__ = (UniqueConstraint("region_id", "week_start_date", name="uq_risk_scores_region_week"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=default_id)
    region_id: Mapped[str] = mapped_column(ForeignKey("admin_boundaries.region_id", ondelete="CASCADE"))
    week_start_date: Mapped[date] = mapped_column(Date, index=True)
    model_version: Mapped[str] = mapped_column(String(64))
    score: Mapped[float] = mapped_column(Float)
    confidence: Mapped[str] = mapped_column(String(16), default="medium")
    driver_contributions: Mapped[dict[str, float]] = mapped_column(JSON, default=dict)
    driver_narrative: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class AlertEventRecord(Base):
    __tablename__ = "alert_events"
    __table_args__ = (UniqueConstraint("region_id", "week_start_date", name="uq_alert_events_region_week"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=default_id)
    region_id: Mapped[str] = mapped_column(ForeignKey("admin_boundaries.region_id", ondelete="CASCADE"), index=True)
    week_start_date: Mapped[date] = mapped_column(Date, index=True)
    severity: Mapped[str] = mapped_column(String(16))
    recommended_action: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default="open")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class ModelTrainingRun(Base):
    __tablename__ = "model_training_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=default_id)
    model_version: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    model_family: Mapped[str] = mapped_column(String(64))
    registry_status: Mapped[str] = mapped_column(String(24), index=True)
    promotion_status: Mapped[str] = mapped_column(String(24))
    feature_build_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    artifact_path: Mapped[str] = mapped_column(Text)
    metadata_path: Mapped[str] = mapped_column(Text)
    model_card_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    training_rows: Mapped[int] = mapped_column(Integer)
    training_weeks: Mapped[int] = mapped_column(Integer)
    evaluation_splits: Mapped[int] = mapped_column(Integer)
    trained_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)
    promoted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    run_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class ScoringRunRecord(Base):
    __tablename__ = "scoring_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=default_id)
    run_scope: Mapped[str] = mapped_column(String(24), index=True)
    run_status: Mapped[str] = mapped_column(String(24), index=True)
    model_version: Mapped[str] = mapped_column(String(64), index=True)
    feature_build_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    latest_week_start_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    weeks_scored: Mapped[int] = mapped_column(Integer)
    rows_scored: Mapped[int] = mapped_column(Integer)
    rows_inserted: Mapped[int] = mapped_column(Integer)
    rows_updated: Mapped[int] = mapped_column(Integer)
    alerts_created_or_updated: Mapped[int] = mapped_column(Integer)
    alerts_removed: Mapped[int] = mapped_column(Integer)
    medium_or_higher_alerts: Mapped[int] = mapped_column(Integer)
    high_alerts: Mapped[int] = mapped_column(Integer)
    medium_or_higher_alert_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    high_alert_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    average_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    non_ok_quality_rows: Mapped[int] = mapped_column(Integer, default=0)
    feature_freshness: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    feature_drift: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    alert_volume: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    executed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
