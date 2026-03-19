from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class RegionSummary(ORMModel):
    region_id: str
    name: str
    risk_level: Literal["low", "medium", "high"]


class RiskSnapshot(ORMModel):
    region_id: str
    week: str
    score: float = Field(ge=0.0, le=1.0)
    confidence: Literal["low", "medium", "high"]
    top_drivers: list[str]


class RiskHistoryPoint(ORMModel):
    week: str
    score: float = Field(ge=0.0, le=1.0)


class DriverBreakdown(ORMModel):
    region_id: str
    week: str
    drivers: dict[str, float]
    narrative: str


class AlertEvent(ORMModel):
    region_id: str
    week: str
    severity: Literal["low", "medium", "high"]
    recommended_action: str


class AlertResolveResponse(ORMModel):
    region_id: str
    week: str
    status: str
    message: str


class RiskAllWeeksRow(ORMModel):
    region_id: str
    week: str
    score: float = Field(ge=0.0, le=1.0)
    confidence: Literal["low", "medium", "high"]


class DataQualityRow(ORMModel):
    region_id: str
    week: str
    quality_flag: str
    rainfall_total_mm_7d: float | None
    confidence: str


class GeoJSONFeature(BaseModel):
    type: Literal["Feature"] = "Feature"
    geometry: dict[str, Any]
    properties: dict[str, Any]


class GeoJSONFeatureCollection(BaseModel):
    type: Literal["FeatureCollection"] = "FeatureCollection"
    features: list[GeoJSONFeature]


class ModelMetricSummary(ORMModel):
    average_precision: float | None = Field(default=None, ge=0.0, le=1.0)
    roc_auc: float | None = Field(default=None, ge=0.0, le=1.0)
    brier_score: float = Field(ge=0.0)
    positive_rate: float = Field(ge=0.0, le=1.0)


class FreshnessStatus(ORMModel):
    scope: str
    status: Literal["ok", "warning", "failed", "skipped"]
    latest_week: str | None = None
    reference_date: str | None = None
    age_days: int | None = Field(default=None, ge=0)
    warn_after_days: int = Field(ge=0)
    fail_after_days: int = Field(ge=0)
    message: str


class FeatureDriftDetail(ORMModel):
    feature: str
    status: Literal["ok", "warning", "failed", "skipped"]
    training_mean: float | None = None
    current_mean: float | None = None
    shift_score: float | None = Field(default=None, ge=0.0)
    missing_rate_delta: float = Field(ge=0.0, le=1.0)
    message: str


class DriftStatus(ORMModel):
    scope: str
    status: Literal["ok", "warning", "failed", "skipped"]
    rows: int = Field(ge=0)
    compared_features: int = Field(ge=0)
    warning_features: int = Field(ge=0)
    failed_features: int = Field(ge=0)
    message: str
    top_drift_features: list[FeatureDriftDetail]


class AlertVolumeStatus(ORMModel):
    scope: str
    status: Literal["ok", "warning", "failed", "skipped"]
    rows: int = Field(ge=0)
    medium_or_higher_alerts: int = Field(ge=0)
    high_alerts: int = Field(ge=0)
    medium_or_higher_alert_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    high_alert_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    expected_medium_or_higher_alert_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    expected_high_alert_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    medium_or_higher_rate_delta: float | None = Field(default=None, ge=0.0, le=1.0)
    high_alert_rate_delta: float | None = Field(default=None, ge=0.0, le=1.0)
    warn_rate_delta: float = Field(ge=0.0, le=1.0)
    fail_rate_delta: float = Field(ge=0.0, le=1.0)
    message: str


class ModelStatus(ORMModel):
    status: Literal["promoted", "fallback"]
    model_version: str
    model_family: str
    trained_at: str | None = None
    promoted_at: str | None = None
    feature_build_version: str | None = None
    training_rows: int | None = Field(default=None, ge=0)
    training_weeks: int | None = Field(default=None, ge=0)
    evaluation_splits: int | None = Field(default=None, ge=0)
    evaluation: ModelMetricSummary | None = None
    persistence_baseline: ModelMetricSummary | None = None
    model_card_path: str | None = None
    training_data_freshness: FreshnessStatus | None = None
    scoring_feature_drift: DriftStatus | None = None


class ModelRunSummary(ORMModel):
    model_version: str
    model_family: str
    registry_status: Literal["active", "challenger", "archived", "rejected"]
    promotion_status: Literal["eligible", "rejected"]
    trained_at: str
    promoted_at: str | None = None
    feature_build_version: str | None = None
    training_rows: int = Field(ge=0)
    training_weeks: int = Field(ge=0)
    evaluation_splits: int = Field(ge=0)
    evaluation: ModelMetricSummary | None = None
    persistence_baseline: ModelMetricSummary | None = None
    training_data_freshness: FreshnessStatus | None = None
    alert_thresholds: dict[str, float] | None = None
    promotion_reasons: list[str] = Field(default_factory=list)
    model_card_path: str | None = None


class ModelComparison(ORMModel):
    active_model: ModelRunSummary | None = None
    challenger_model: ModelRunSummary | None = None
    recent_runs: list[ModelRunSummary] = Field(default_factory=list)


class ModelPromotionResponse(ORMModel):
    model_version: str
    status: Literal["promoted", "already_active"]
    message: str
    previous_active_model_version: str | None = None


class ScoringRunSummary(ORMModel):
    run_scope: Literal["latest_week", "all_weeks"]
    run_status: Literal["ok", "warning", "failed", "skipped"]
    executed_at: str
    model_version: str
    feature_build_version: str | None = None
    latest_week: str | None = None
    weeks_scored: int = Field(ge=0)
    rows_scored: int = Field(ge=0)
    rows_inserted: int = Field(ge=0)
    rows_updated: int = Field(ge=0)
    alerts_created_or_updated: int = Field(ge=0)
    alerts_removed: int = Field(ge=0)
    medium_or_higher_alerts: int = Field(ge=0)
    high_alerts: int = Field(ge=0)
    medium_or_higher_alert_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    high_alert_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    average_score: float | None = Field(default=None, ge=0.0, le=1.0)
    max_score: float | None = Field(default=None, ge=0.0, le=1.0)
    non_ok_quality_rows: int = Field(ge=0)
    feature_freshness: FreshnessStatus
    feature_drift: DriftStatus
    alert_volume: AlertVolumeStatus


class ScoringHealth(ORMModel):
    latest_run: ScoringRunSummary | None = None
    recent_runs: list[ScoringRunSummary] = Field(default_factory=list)


class ModelCardDocument(ORMModel):
    model_version: str
    format: Literal["markdown"] = "markdown"
    promoted_at: str | None = None
    content: str


class PilotDataSource(ORMModel):
    key: str
    name: str
    kind: Literal["boundaries", "covariates", "weather", "labels", "demo"]
    status: Literal["live", "partner_pending", "demo", "planned"]
    cadence: str
    uri: str
    notes: str | None = None


class PilotDefinition(ORMModel):
    project_name: str
    pilot_name: str
    country: str
    iso3: str
    admin_level: str
    admin_level_label: str
    outcome_name: str
    outcome_definition: str
    prediction_horizon: str
    decision_statement: str
    intended_users: list[str]
    label_strategy: str
    data_sources: list[PilotDataSource]


class DemoRiskPoint(ORMModel):
    region_id: str
    location_label: str
    latitude: float
    longitude: float
    target_date: str
    rainfall_mm_7d: float
    flood_proxy: float
    sanitation_access_pct: float
    population_density_km2: float
    temperature_c: float
    surface_water_index: float
    risk_score: float = Field(ge=0.0, le=100.0)
    driver_summary: str
