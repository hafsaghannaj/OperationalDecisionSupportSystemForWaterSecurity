export type RiskLevel = "low" | "medium" | "high";

export interface RegionSummary {
  region_id: string;
  name: string;
  risk_level: RiskLevel;
}

export interface RiskSnapshot {
  region_id: string;
  week: string;
  score: number;
  confidence: RiskLevel;
  top_drivers: string[];
}

export interface RiskHistoryPoint {
  week: string;
  score: number;
}

export interface RiskAllWeeksRow {
  region_id: string;
  week: string;
  score: number;
  confidence: RiskLevel;
}

export interface DriverBreakdown {
  region_id: string;
  week: string;
  drivers: Record<string, number>;
  narrative: string;
}

export interface AlertEvent {
  region_id: string;
  week: string;
  severity: RiskLevel;
  recommended_action: string;
}

export interface DataQualityRow {
  region_id: string;
  week: string;
  quality_flag: string;
  rainfall_total_mm_7d: number | null;
  confidence: string;
}

export interface ModelMetricSummary {
  average_precision: number | null;
  roc_auc: number | null;
  brier_score: number;
  positive_rate: number;
}

export interface FreshnessStatus {
  scope: string;
  status: "ok" | "warning" | "failed" | "skipped";
  latest_week: string | null;
  reference_date: string | null;
  age_days: number | null;
  warn_after_days: number;
  fail_after_days: number;
  message: string;
}

export interface FeatureDriftDetail {
  feature: string;
  status: "ok" | "warning" | "failed" | "skipped";
  training_mean: number | null;
  current_mean: number | null;
  shift_score: number | null;
  missing_rate_delta: number;
  message: string;
}

export interface DriftStatus {
  scope: string;
  status: "ok" | "warning" | "failed" | "skipped";
  rows: number;
  compared_features: number;
  warning_features: number;
  failed_features: number;
  message: string;
  top_drift_features: FeatureDriftDetail[];
}

export interface AlertVolumeStatus {
  scope: string;
  status: "ok" | "warning" | "failed" | "skipped";
  rows: number;
  medium_or_higher_alerts: number;
  high_alerts: number;
  medium_or_higher_alert_rate: number | null;
  high_alert_rate: number | null;
  expected_medium_or_higher_alert_rate: number | null;
  expected_high_alert_rate: number | null;
  medium_or_higher_rate_delta: number | null;
  high_alert_rate_delta: number | null;
  warn_rate_delta: number;
  fail_rate_delta: number;
  message: string;
}

export interface ModelStatus {
  status: "promoted" | "fallback";
  model_version: string;
  model_family: string;
  trained_at: string | null;
  promoted_at: string | null;
  feature_build_version: string | null;
  training_rows: number | null;
  training_weeks: number | null;
  evaluation_splits: number | null;
  evaluation: ModelMetricSummary | null;
  persistence_baseline: ModelMetricSummary | null;
  training_data_freshness: FreshnessStatus | null;
  scoring_feature_drift: DriftStatus | null;
}

export interface ModelRunSummary {
  model_version: string;
  model_family: string;
  registry_status: "active" | "challenger" | "archived" | "rejected";
  promotion_status: "eligible" | "rejected";
  trained_at: string;
  promoted_at: string | null;
  feature_build_version: string | null;
  training_rows: number;
  training_weeks: number;
  evaluation_splits: number;
  evaluation: ModelMetricSummary | null;
  persistence_baseline: ModelMetricSummary | null;
  training_data_freshness: FreshnessStatus | null;
  alert_thresholds: Record<string, number> | null;
  promotion_reasons: string[];
  model_card_path: string | null;
}

export interface ModelComparison {
  active_model: ModelRunSummary | null;
  challenger_model: ModelRunSummary | null;
  recent_runs: ModelRunSummary[];
}

export interface ScoringRunSummary {
  run_scope: "latest_week" | "all_weeks";
  run_status: "ok" | "warning" | "failed" | "skipped";
  executed_at: string;
  model_version: string;
  feature_build_version: string | null;
  latest_week: string | null;
  weeks_scored: number;
  rows_scored: number;
  rows_inserted: number;
  rows_updated: number;
  alerts_created_or_updated: number;
  alerts_removed: number;
  medium_or_higher_alerts: number;
  high_alerts: number;
  medium_or_higher_alert_rate: number | null;
  high_alert_rate: number | null;
  average_score: number | null;
  max_score: number | null;
  non_ok_quality_rows: number;
  feature_freshness: FreshnessStatus;
  feature_drift: DriftStatus;
  alert_volume: AlertVolumeStatus;
}

export interface ScoringHealth {
  latest_run: ScoringRunSummary | null;
  recent_runs: ScoringRunSummary[];
}

export interface PilotDataSource {
  key: string;
  name: string;
  kind: "boundaries" | "covariates" | "weather" | "labels" | "demo";
  status: "live" | "partner_pending" | "demo" | "planned";
  cadence: string;
  uri: string;
  notes: string | null;
}

export interface PilotDefinition {
  project_name: string;
  pilot_name: string;
  country: string;
  iso3: string;
  admin_level: string;
  admin_level_label: string;
  outcome_name: string;
  outcome_definition: string;
  prediction_horizon: string;
  decision_statement: string;
  intended_users: string[];
  label_strategy: string;
  data_sources: PilotDataSource[];
}

export interface DemoRiskPoint {
  region_id: string;
  location_label: string;
  latitude: number;
  longitude: number;
  target_date: string;
  rainfall_mm_7d: number;
  flood_proxy: number;
  sanitation_access_pct: number;
  population_density_km2: number;
  temperature_c: number;
  surface_water_index: number;
  risk_score: number;
  driver_summary: string;
}

export interface CagAnswer {
  answer: string;
  used_region: string | null;
  cache_type: string;
}

export interface OperatorAuditLogEntry {
  id: string;
  action_type: string;
  target_type: string;
  target_id: string;
  operator_id: string | null;
  region_id: string | null;
  week: string | null;
  model_version: string | null;
  note: string | null;
  event_metadata: Record<string, unknown>;
  created_at: string;
}

export interface DashboardRiskRow extends RiskSnapshot {
  region_name: string;
  risk_level: RiskLevel;
}

export interface DashboardAlertRow extends AlertEvent {
  region_name: string;
  score: number | null;
  top_drivers: string[];
}

export interface DashboardData {
  latestRisk: DashboardRiskRow[];
  allWeeksRisk: RiskAllWeeksRow[];
  alerts: DashboardAlertRow[];
  focusRegion: DashboardRiskRow | null;
  focusHistory: RiskHistoryPoint[];
  focusDrivers: DriverBreakdown | null;
  modelStatus: ModelStatus | null;
  modelComparison: ModelComparison | null;
  scoringHealth: ScoringHealth | null;
  dataQuality: DataQualityRow[];
  pilotDefinition: PilotDefinition | null;
  demoRiskPoints: DemoRiskPoint[];
  auditLogs: OperatorAuditLogEntry[];
  fetchedAt: string;
  apiHealthy: boolean;
  error?: string;
}
