import type {
  AlertEvent,
  CagAnswer,
  DashboardAlertRow,
  DashboardData,
  DashboardRiskRow,
  DataQualityRow,
  DemoRiskPoint,
  DriverBreakdown,
  ModelComparison,
  ModelStatus,
  OperatorAuditLogEntry,
  PilotDefinition,
  RegionSummary,
  RiskAllWeeksRow,
  RiskHistoryPoint,
  RiskLevel,
  RiskSnapshot,
  ScoringHealth,
} from "./types";

const rawBaseUrl =
  process.env.ODSSWS_API_BASE_URL ??
  process.env.AQUAINTEL_API_BASE_URL ??
  process.env.NEXT_PUBLIC_API_BASE_URL ??
  "http://localhost:8000";

const apiBaseUrl = rawBaseUrl.replace(/\/$/, "");

function riskLevelFromScore(score: number): RiskLevel {
  if (score >= 0.7) return "high";
  if (score >= 0.4) return "medium";
  return "low";
}

function buildUrl(path: string): string {
  return `${apiBaseUrl}${path}`;
}

async function fetchJson<T>(path: string, allowNotFound = false): Promise<T | null> {
  const response = await fetch(buildUrl(path), { cache: "no-store" });
  if (allowNotFound && response.status === 404) return null;
  if (!response.ok) throw new Error(`Request failed for ${path}: ${response.status}`);
  return (await response.json()) as T;
}

function joinRiskWithRegions(regions: RegionSummary[], latestRisk: RiskSnapshot[]): DashboardRiskRow[] {
  const regionNames = new Map(regions.map((r) => [r.region_id, r.name]));
  return latestRisk.map((risk) => ({
    ...risk,
    region_name: regionNames.get(risk.region_id) ?? risk.region_id,
    risk_level: riskLevelFromScore(risk.score),
  }));
}

function joinAlertsWithRisk(
  regions: RegionSummary[],
  riskRows: DashboardRiskRow[],
  alerts: AlertEvent[]
): DashboardAlertRow[] {
  const regionNames = new Map(regions.map((r) => [r.region_id, r.name]));
  const riskByRegionId = new Map(riskRows.map((risk) => [risk.region_id, risk]));
  return alerts.map((alert) => {
    const risk = riskByRegionId.get(alert.region_id);
    return {
      ...alert,
      region_name: regionNames.get(alert.region_id) ?? alert.region_id,
      score: risk?.score ?? null,
      top_drivers: risk?.top_drivers ?? [],
    };
  });
}

function fetchedAtLabel(): string {
  return new Intl.DateTimeFormat("en-US", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: "UTC",
  }).format(new Date());
}

export async function resolveAlert(region_id: string, week: string): Promise<void> {
  const encoded_week = encodeURIComponent(week);
  const response = await fetch(buildUrl(`/alerts/${encodeURIComponent(region_id)}/${encoded_week}/resolve`), {
    method: "PATCH",
  });
  if (!response.ok) throw new Error(`Failed to resolve alert: ${response.status}`);
}

export async function acknowledgeAlert(region_id: string, week: string): Promise<void> {
  const encoded_week = encodeURIComponent(week);
  const response = await fetch(buildUrl(`/alerts/${encodeURIComponent(region_id)}/${encoded_week}/acknowledge`), {
    method: "POST",
  });
  if (!response.ok) throw new Error(`Failed to acknowledge alert: ${response.status}`);
}

export async function createFieldAction(region_id: string, week: string, action: string, note: string): Promise<void> {
  const response = await fetch(buildUrl("/field-actions"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ region_id, week, action, note }),
  });
  if (!response.ok) throw new Error(`Failed to create field action: ${response.status}`);
}

export async function promoteModel(modelVersion: string): Promise<void> {
  const response = await fetch(buildUrl(`/model/runs/${encodeURIComponent(modelVersion)}/promote`), {
    method: "POST",
  });
  if (!response.ok) throw new Error(`Failed to promote model: ${response.status}`);
}

export async function askCag(question: string, regionKey?: string): Promise<CagAnswer> {
  const response = await fetch(buildUrl("/cag/ask"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      question,
      region_key: regionKey ?? null,
    }),
  });
  if (!response.ok) throw new Error(`Failed to ask CAG assistant: ${response.status}`);
  return response.json() as Promise<CagAnswer>;
}

export async function fetchDashboardData(): Promise<DashboardData> {
  try {
    const [
      regionsRaw,
      latestRiskRaw,
      alertsRaw,
      allWeeksRaw,
      modelStatusRaw,
      modelComparisonRaw,
      scoringHealthRaw,
      qualityRaw,
      pilotDefinitionRaw,
      demoRiskPointsRaw,
      auditLogsRaw,
    ] = await Promise.all([
      fetchJson<RegionSummary[]>("/regions"),
      fetchJson<RiskSnapshot[]>("/risk/latest"),
      fetchJson<AlertEvent[]>("/alerts"),
      fetchJson<RiskAllWeeksRow[]>("/risk/all-weeks"),
      fetchJson<ModelStatus>("/model/status", true),
      fetchJson<ModelComparison>("/model/compare", true),
      fetchJson<ScoringHealth>("/scoring/health", true),
      fetchJson<DataQualityRow[]>("/data/quality"),
      fetchJson<PilotDefinition>("/pilot", true),
      fetchJson<DemoRiskPoint[]>("/demo/risk-points", true),
      fetchJson<OperatorAuditLogEntry[]>("/audit/logs", true),
    ]);

    const regions = regionsRaw ?? [];
    const latestRisk = joinRiskWithRegions(regions, latestRiskRaw ?? []);
    const alerts = joinAlertsWithRisk(regions, latestRisk, alertsRaw ?? []);

    const focusRegion = latestRisk[0] ?? null;

    if (!focusRegion) {
      return {
        latestRisk,
        allWeeksRisk: allWeeksRaw ?? [],
        alerts,
        focusRegion: null,
        focusHistory: [],
        focusDrivers: null,
        modelStatus: modelStatusRaw,
        modelComparison: modelComparisonRaw,
        scoringHealth: scoringHealthRaw,
        dataQuality: qualityRaw ?? [],
        pilotDefinition: pilotDefinitionRaw,
        demoRiskPoints: demoRiskPointsRaw ?? [],
        auditLogs: auditLogsRaw ?? [],
        fetchedAt: fetchedAtLabel(),
        apiHealthy: true,
      };
    }

    const [focusHistoryRaw, focusDriversRaw] = await Promise.all([
      fetchJson<RiskHistoryPoint[]>(`/risk/history?region_id=${encodeURIComponent(focusRegion.region_id)}`, true),
      fetchJson<DriverBreakdown>(
        `/drivers/${encodeURIComponent(focusRegion.region_id)}/${encodeURIComponent(focusRegion.week)}`,
        true
      ),
    ]);

    return {
      latestRisk,
      allWeeksRisk: allWeeksRaw ?? [],
      alerts,
      focusRegion,
      focusHistory: focusHistoryRaw ?? [],
      focusDrivers: focusDriversRaw,
      modelStatus: modelStatusRaw,
      modelComparison: modelComparisonRaw,
      scoringHealth: scoringHealthRaw,
      dataQuality: qualityRaw ?? [],
      pilotDefinition: pilotDefinitionRaw,
      demoRiskPoints: demoRiskPointsRaw ?? [],
      auditLogs: auditLogsRaw ?? [],
      fetchedAt: fetchedAtLabel(),
      apiHealthy: true,
    };
  } catch (error) {
    return {
      latestRisk: [],
      allWeeksRisk: [],
      alerts: [],
      focusRegion: null,
      focusHistory: [],
      focusDrivers: null,
      modelStatus: null,
      modelComparison: null,
      scoringHealth: null,
      dataQuality: [],
      pilotDefinition: null,
      demoRiskPoints: [],
      auditLogs: [],
      fetchedAt: fetchedAtLabel(),
      apiHealthy: false,
      error: error instanceof Error ? error.message : "Unknown API error.",
    };
  }
}
