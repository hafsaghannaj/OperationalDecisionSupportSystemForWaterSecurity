"use client";

import dynamic from "next/dynamic";
import { useState, useEffect, useCallback } from "react";
import type {
  CagAnswer,
  DashboardData,
  DashboardRiskRow,
  DataQualityRow,
  DemoRiskPoint,
  DriftStatus,
  FreshnessStatus,
  ModelComparison,
  ModelRunSummary,
  ModelStatus,
  OperatorAuditLogEntry,
  PilotDefinition,
  RiskHistoryPoint,
  ScoringHealth,
} from "../lib/types";
import { acknowledgeAlert, askCag, createFieldAction, promoteModel, resolveAlert } from "../lib/api";

const TacticalMap = dynamic(() => import("./tactical-map"), {
  ssr: false,
  loading: () => <div className="map-loading">◈ INITIALIZING TACTICAL MAP…</div>,
});

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
const REFRESH_SECONDS = 300;

function shortWeek(week: string) {
  return week.replace("-W", "/W");
}

function scoreColor(score: number) {
  if (score >= 0.7) return "var(--red)";
  if (score >= 0.4) return "var(--amber)";
  return "var(--green)";
}

function qualityColor(flag: string) {
  if (flag === "ok") return "var(--green)";
  if (flag === "missing_static_and_weather") return "var(--red)";
  return "var(--amber)";
}

function guardrailColor(status: "ok" | "warning" | "failed" | "skipped" | undefined) {
  if (status === "ok") return "var(--green)";
  if (status === "warning") return "var(--amber)";
  if (status === "failed") return "var(--red)";
  return "var(--label)";
}

function freshnessLabel(freshness: FreshnessStatus | null | undefined) {
  if (!freshness) return "NOT RECORDED";
  if (freshness.age_days === null) return freshness.status.toUpperCase();
  return `${freshness.status.toUpperCase()} · ${freshness.age_days}D OLD`;
}

function driftLabel(drift: DriftStatus | null | undefined) {
  if (!drift) return "NOT RECORDED";
  if (drift.status === "skipped") return "SKIPPED";
  return `${drift.status.toUpperCase()} · ${drift.warning_features}W ${drift.failed_features}F`;
}

function rateLabel(value: number | null | undefined) {
  if (value == null) return "—";
  return `${(value * 100).toFixed(1)}%`;
}

function runStatusColor(run: ModelRunSummary | null | undefined) {
  if (!run) return "var(--label)";
  if (run.registry_status === "active") return "var(--green)";
  if (run.registry_status === "challenger") return "var(--amber)";
  if (run.registry_status === "rejected") return "var(--red)";
  return "var(--blue-hi)";
}

function sourceStatusColor(status: "live" | "partner_pending" | "demo" | "planned") {
  if (status === "live") return "var(--green)";
  if (status === "partner_pending") return "var(--amber)";
  if (status === "demo") return "var(--blue-hi)";
  return "var(--label)";
}

/* ── Sub-components ─────────────────────────────────────── */

function RiskHistory({ history }: { history: RiskHistoryPoint[] }) {
  if (!history.length) {
    return (
      <div className="empty-state">
        <span className="empty-state-icon">◌</span>
        NO HISTORY DATA AVAILABLE
      </div>
    );
  }
  const max = Math.max(...history.map((h) => h.score), 0.01);
  return (
    <div className="chart-container">
      <div className="chart-grid">
        <div className="chart-grid-lines">
          {[0, 1, 2, 3].map((i) => (
            <div className="chart-grid-line" key={i} />
          ))}
        </div>
        {history.map((point) => {
          const color = scoreColor(point.score);
          return (
            <div className="spark-col" key={point.week}>
              <div className="spark-val" style={{ color }}>{point.score.toFixed(2)}</div>
              <div className="spark-bar-wrap">
                <div
                  className="spark-bar"
                  style={{
                    height: `${Math.max(4, (point.score / max) * 100)}%`,
                    background: `linear-gradient(180deg, ${color}cc, ${color}33)`,
                    boxShadow: `0 0 8px ${color}50`,
                  }}
                />
              </div>
              <div className="spark-label">{shortWeek(point.week)}</div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function RunCompareCard({ title, run }: { title: string; run: ModelRunSummary | null | undefined }) {
  if (!run) {
    return (
      <div className="focus-metric" style={{ minHeight: "8rem" }}>
        <div className="focus-metric-label">{title}</div>
        <div className="focus-metric-value" style={{ color: "var(--muted)" }}>—</div>
        <div style={{ fontSize: "0.63rem", color: "var(--muted)", marginTop: "0.3rem" }}>NO REGISTERED MODEL</div>
      </div>
    );
  }
  return (
    <div className="focus-metric" style={{ minHeight: "8rem" }}>
      <div className="focus-metric-label">{title}</div>
      <div className="focus-metric-value" style={{ color: runStatusColor(run), fontSize: "0.85rem" }}>
        {run.registry_status.toUpperCase()}
      </div>
      <div style={{ fontSize: "0.62rem", color: "var(--label)", marginTop: "0.35rem", lineHeight: 1.7 }}>
        <div>{run.model_family.toUpperCase()}</div>
        <div>AUCPR {run.evaluation?.average_precision?.toFixed(3) ?? "—"} · SPLITS {run.evaluation_splits}</div>
        <div>GATE {run.promotion_status.toUpperCase()}</div>
      </div>
    </div>
  );
}

function ModelPanel({
  model,
  comparison,
  scoringHealth,
  onPromote,
  isPromoting,
  actionError,
}: {
  model: ModelStatus;
  comparison: ModelComparison | null;
  scoringHealth: ScoringHealth | null;
  onPromote: (modelVersion: string) => Promise<void>;
  isPromoting: boolean;
  actionError: string | null;
}) {
  const ev = model.evaluation;
  const base = model.persistence_baseline;
  const freshness = model.training_data_freshness;
  const drift = model.scoring_feature_drift;
  const activeRun = comparison?.active_model;
  const challengerRun = comparison?.challenger_model;
  const latestScoringRun = scoringHealth?.latest_run;

  const statusColor =
    model.status === "promoted" ? "var(--green)"
    : model.status === "fallback" ? "var(--amber)"
    : "var(--label)";

  return (
    <div className="model-status-body">
      {/* Header row */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: "1rem", marginBottom: "1rem" }}>
        <div>
          <div className="model-version-badge">{model.model_version}</div>
          <div style={{ marginTop: "0.25rem" }}>
            <span className="model-family-tag">{model.model_family.toUpperCase()}</span>
          </div>
        </div>
        <span
          className="model-status-tag"
          style={{ color: statusColor, borderColor: statusColor + "60", background: statusColor + "12" }}
        >
          {model.status.toUpperCase()}
        </span>
      </div>

      {/* Key metrics */}
      {ev && (
        <>
          <div className="section-label">Evaluation Metrics</div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: "0.55rem", marginBottom: "0.85rem" }}>
            {[
              { label: "AUCPR", value: ev.average_precision?.toFixed(3) ?? "—", color: "var(--blue-hi)" },
              { label: "ROC-AUC", value: ev.roc_auc?.toFixed(3) ?? "—", color: "var(--blue-hi)" },
              { label: "BRIER", value: ev.brier_score?.toFixed(3) ?? "—", color: "var(--cyan)" },
            ].map(({ label, value, color }) => (
              <div className="focus-metric" key={label}>
                <div className="focus-metric-label">{label}</div>
                <div className="focus-metric-value" style={{ color }}>{value}</div>
              </div>
            ))}
          </div>
        </>
      )}

      {/* Baseline comparison */}
      {base && (
        <>
          <div className="section-label">vs Persistence Baseline</div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: "0.55rem", marginBottom: "0.85rem" }}>
            <div className="focus-metric">
              <div className="focus-metric-label">Base AUCPR</div>
              <div className="focus-metric-value">{base.average_precision?.toFixed(3) ?? "—"}</div>
            </div>
            <div className="focus-metric">
              <div className="focus-metric-label">Base ROC</div>
              <div className="focus-metric-value">{base.roc_auc?.toFixed(3) ?? "—"}</div>
            </div>
            <div className="focus-metric">
              <div className="focus-metric-label">Splits</div>
              <div className="focus-metric-value">{model.evaluation_splits ?? "—"}</div>
            </div>
          </div>
        </>
      )}

      {/* Guardrails */}
      {(freshness || drift) && (
        <>
          <div className="section-label">Operational Guardrails</div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.55rem", marginBottom: "0.85rem" }}>
            <div className="focus-metric">
              <div className="focus-metric-label">Training Freshness</div>
              <div className="focus-metric-value" style={{ color: guardrailColor(freshness?.status), fontSize: "0.82rem" }}>
                {freshnessLabel(freshness)}
              </div>
            </div>
            <div className="focus-metric">
              <div className="focus-metric-label">Scoring Drift</div>
              <div className="focus-metric-value" style={{ color: guardrailColor(drift?.status), fontSize: "0.82rem" }}>
                {driftLabel(drift)}
              </div>
            </div>
          </div>
          {freshness?.message && (
            <div className="model-note">{freshness.message}</div>
          )}
        </>
      )}

      {/* Latest scoring run */}
      {latestScoringRun && (
        <>
          <div className="section-label">Latest Scoring Run</div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(2, 1fr)", gap: "0.55rem", marginBottom: "0.85rem" }}>
            {[
              { label: "Status", value: latestScoringRun.run_status.toUpperCase(), color: guardrailColor(latestScoringRun.run_status) },
              { label: "Latest Week", value: latestScoringRun.latest_week ?? "—", color: undefined },
              { label: "Rows Scored", value: String(latestScoringRun.rows_scored), color: undefined },
              { label: "Med+ Alerts", value: `${latestScoringRun.medium_or_higher_alerts} (${rateLabel(latestScoringRun.medium_or_higher_alert_rate)})`, color: undefined },
            ].map(({ label, value, color }) => (
              <div className="focus-metric" key={label}>
                <div className="focus-metric-label">{label}</div>
                <div className="focus-metric-value" style={color ? { color, fontSize: "0.82rem" } : { fontSize: "0.82rem" }}>{value}</div>
              </div>
            ))}
          </div>
          <div className="model-note">{latestScoringRun.alert_volume.message}</div>
        </>
      )}

      {/* Champion / Challenger */}
      {comparison && (
        <>
          <div className="section-label">Champion / Challenger</div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.55rem", marginBottom: "0.85rem" }}>
            <RunCompareCard title="CHAMPION" run={activeRun} />
            <RunCompareCard title="CHALLENGER" run={challengerRun} />
          </div>

          {challengerRun?.registry_status === "challenger" && challengerRun.promotion_status === "eligible" && (
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: "0.75rem", marginBottom: "0.85rem" }}>
              <div style={{ fontSize: "0.63rem", color: "var(--label)", lineHeight: 1.5 }}>
                Manual gate — activate to replace the current scoring path.
              </div>
              <button
                className="promote-btn"
                onClick={() => void onPromote(challengerRun.model_version)}
                disabled={isPromoting}
              >
                {isPromoting ? "ACTIVATING…" : activeRun ? "PROMOTE" : "ACTIVATE"}
              </button>
            </div>
          )}

          {actionError && (
            <div className="model-note" style={{ color: "var(--red)", borderColor: "rgba(240,48,64,0.3)" }}>
              {actionError}
            </div>
          )}
        </>
      )}

      {model.trained_at && (
        <div className="narrative">
          Trained {model.trained_at} · {model.feature_build_version ?? "—"} · {model.training_rows ?? "?"} rows / {model.training_weeks ?? "?"} weeks
        </div>
      )}
    </div>
  );
}

function QualityPanel({ quality }: { quality: DataQualityRow[] }) {
  if (!quality.length) {
    return (
      <div className="empty-state">
        <span className="empty-state-icon">◻</span>
        NO QUALITY DATA AVAILABLE
      </div>
    );
  }
  return (
    <div style={{ overflowY: "auto", flex: 1, minHeight: 0 }}>
      {quality.map((row) => {
        const color = qualityColor(row.quality_flag);
        return (
          <div
            key={`${row.region_id}-${row.week}`}
            className="quality-row"
            style={{ borderLeftColor: color }}
          >
            <div className="quality-row-main">
              <div className="quality-region">{row.region_id} <span style={{ color: "var(--muted)", fontWeight: 400 }}>·</span> {shortWeek(row.week)}</div>
              <div className="quality-detail">
                {row.rainfall_total_mm_7d != null
                  ? `${row.rainfall_total_mm_7d.toFixed(1)}mm rain`
                  : "no rain data"} · conf: {row.confidence}
              </div>
            </div>
            <span
              className="severity-tag"
              style={{
                color,
                borderColor: color + "55",
                background: color + "15",
                fontSize: "0.57rem",
              }}
            >
              {row.quality_flag.replace(/_/g, " ").toUpperCase()}
            </span>
          </div>
        );
      })}
    </div>
  );
}

function OpsPanel({
  pilot,
  demoRiskPoints,
  auditLogs,
  fieldActionNote,
  question,
  answer,
  loading,
  error,
  onQuestionChange,
  onAsk,
  onFieldActionNoteChange,
  onCreateFieldAction,
}: {
  pilot: PilotDefinition | null;
  demoRiskPoints: DemoRiskPoint[];
  auditLogs: OperatorAuditLogEntry[];
  fieldActionNote: string;
  question: string;
  answer: CagAnswer | null;
  loading: boolean;
  error: string | null;
  onQuestionChange: (value: string) => void;
  onAsk: (question: string) => Promise<void>;
  onFieldActionNoteChange: (value: string) => void;
  onCreateFieldAction: () => Promise<void>;
}) {
  if (!pilot) {
    return (
      <div className="empty-state">
        <span className="empty-state-icon">◬</span>
        NO PILOT DEFINITION AVAILABLE
      </div>
    );
  }

  return (
    <div className="ops-body">
      <div className="section-label">Locked Pilot</div>
      <div className="focus-metric-row">
        <div className="focus-metric">
          <div className="focus-metric-label">Geography</div>
          <div className="focus-metric-value">{pilot.country} · {pilot.admin_level_label}</div>
        </div>
        <div className="focus-metric">
          <div className="focus-metric-label">Horizon</div>
          <div className="focus-metric-value">{pilot.prediction_horizon}</div>
        </div>
      </div>
      <div className="model-note">{pilot.outcome_name}</div>
      <p className="narrative">{pilot.decision_statement}</p>

      <div className="section-label">Real Data Path</div>
      <div className="ops-source-list">
        {pilot.data_sources.map((source) => {
          const color = sourceStatusColor(source.status);
          return (
            <div className="ops-source-row" key={source.key}>
              <div>
                <div className="ops-source-name">{source.name}</div>
                <div className="ops-source-meta">{source.kind.toUpperCase()} · {source.cadence}</div>
                {source.notes && <div className="ops-source-note">{source.notes}</div>}
              </div>
              <span
                className="severity-tag"
                style={{
                  color,
                  borderColor: `${color}55`,
                  background: `${color}15`,
                }}
              >
                {source.status.replace(/_/g, " ").toUpperCase()}
              </span>
            </div>
          );
        })}
      </div>

      <div className="section-label">Demo Preview</div>
      <div className="ops-demo-list">
        {demoRiskPoints.map((point) => (
          <div className="ops-demo-row" key={`${point.region_id}-${point.target_date}`}>
            <div>
              <div className="ops-source-name">{point.location_label}</div>
              <div className="ops-source-meta">{point.region_id} · {point.target_date}</div>
            </div>
            <div className="ops-demo-score" style={{ color: point.risk_score >= 70 ? "var(--red)" : point.risk_score >= 40 ? "var(--amber)" : "var(--green)" }}>
              {point.risk_score.toFixed(1)}
            </div>
          </div>
        ))}
      </div>

      <div className="section-label">CAG Assistant</div>
      <div className="ops-assistant">
        <input
          className="ops-input"
          value={question}
          onChange={(event) => onQuestionChange(event.target.value)}
          placeholder="Ask for next-step guidance or response actions"
        />
        <div className="ops-action-row">
          <button className="promote-btn" disabled={loading || !question.trim()} onClick={() => void onAsk(question)}>
            {loading ? "ASKING…" : "ASK"}
          </button>
          <button className="resolve-btn" onClick={() => onQuestionChange("What actions are recommended at elevated risk?")}>
            LOAD PROMPT
          </button>
        </div>
        {error && <div className="model-note" style={{ color: "var(--red)", borderColor: "rgba(240,48,64,0.3)" }}>{error}</div>}
        {answer && (
          <div className="model-note">
            <div style={{ marginBottom: "0.35rem", color: "var(--blue-hi)" }}>
              {answer.cache_type.toUpperCase()} CACHE{answer.used_region ? ` · ${answer.used_region.toUpperCase()}` : ""}
            </div>
            {answer.answer}
          </div>
        )}
      </div>

      <div className="section-label">Field Action Note</div>
      <div className="ops-assistant" style={{ marginBottom: "0.95rem" }}>
        <input
          className="ops-input"
          value={fieldActionNote}
          onChange={(event) => onFieldActionNoteChange(event.target.value)}
          placeholder="Log a field action note for the selected district week"
        />
        <div className="ops-action-row">
          <button className="promote-btn" onClick={() => void onCreateFieldAction()} disabled={!fieldActionNote.trim()}>
            LOG NOTE
          </button>
        </div>
      </div>

      <div className="section-label">Recent Audit Trail</div>
      <div className="ops-source-list">
        {auditLogs.length ? auditLogs.map((entry) => (
          <div className="ops-source-row" key={entry.id}>
            <div>
              <div className="ops-source-name">{entry.action_type.replace(/_/g, " ").toUpperCase()}</div>
              <div className="ops-source-meta">
                {entry.region_id ?? entry.target_id}
                {entry.week ? ` · ${entry.week}` : ""}
                {entry.operator_id ? ` · ${entry.operator_id}` : ""}
              </div>
              {entry.note && <div className="ops-source-note">{entry.note}</div>}
            </div>
            <span className="severity-tag" style={{ color: "var(--blue-hi)", borderColor: "rgba(34,180,255,0.35)", background: "rgba(34,180,255,0.08)" }}>
              {entry.target_type.toUpperCase()}
            </span>
          </div>
        )) : (
          <div className="model-note">No audit entries recorded yet.</div>
        )}
      </div>
    </div>
  );
}

/* ── Main Shell ─────────────────────────────────────────── */

export function DashboardShell({ data: initialData }: { data: DashboardData }) {
  const [data, setData] = useState(initialData);
  const [selectedRegionId, setSelectedRegionId] = useState<string | null>(
    initialData.focusRegion?.region_id ?? null
  );
  const [activeTab, setActiveTab] = useState<"alerts" | "quality" | "model" | "ops">("alerts");
  const [countdown, setCountdown] = useState(REFRESH_SECONDS);
  const [isPromoting, setIsPromoting] = useState(false);
  const [modelActionError, setModelActionError] = useState<string | null>(null);
  const [assistantQuestion, setAssistantQuestion] = useState("What actions are recommended at elevated risk?");
  const [assistantAnswer, setAssistantAnswer] = useState<CagAnswer | null>(null);
  const [assistantLoading, setAssistantLoading] = useState(false);
  const [assistantError, setAssistantError] = useState<string | null>(null);
  const [fieldActionNote, setFieldActionNote] = useState("");

  const focusRegion: DashboardRiskRow | null =
    data.latestRisk.find((r) => r.region_id === selectedRegionId) ?? data.focusRegion;

  const [focusHistory, setFocusHistory] = useState(initialData.focusHistory);
  const [focusDrivers, setFocusDrivers] = useState(initialData.focusDrivers);

  useEffect(() => {
    if (!selectedRegionId || !focusRegion) return;
    const week = focusRegion.week;
    Promise.all([
      fetch(`${API_BASE}/risk/history?region_id=${encodeURIComponent(selectedRegionId)}`).then((r) => r.ok ? r.json() : []),
      fetch(`${API_BASE}/drivers/${encodeURIComponent(selectedRegionId)}/${encodeURIComponent(week)}`).then((r) => r.ok ? r.json() : null),
    ]).then(([hist, drv]) => {
      setFocusHistory(hist ?? []);
      setFocusDrivers(drv);
    }).catch(() => {});
  }, [selectedRegionId]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const tick = setInterval(() => {
      setCountdown((c) => {
        if (c <= 1) { window.location.reload(); return REFRESH_SECONDS; }
        return c - 1;
      });
    }, 1000);
    return () => clearInterval(tick);
  }, []);

  const handleResolveAlert = useCallback(async (regionId: string, week: string) => {
    try {
      await resolveAlert(regionId, week);
      setData((prev) => ({
        ...prev,
        alerts: prev.alerts.filter((a) => !(a.region_id === regionId && a.week === week)),
      }));
    } catch { /* silent */ }
  }, []);

  const handleAcknowledgeAlert = useCallback(async (regionId: string, week: string) => {
    try {
      await acknowledgeAlert(regionId, week);
      window.location.reload();
    } catch { /* silent */ }
  }, []);

  const handlePromoteModel = useCallback(async (modelVersion: string) => {
    setModelActionError(null);
    setIsPromoting(true);
    try {
      await promoteModel(modelVersion);
      window.location.reload();
    } catch (error) {
      setModelActionError(error instanceof Error ? error.message : "Promotion failed.");
    } finally {
      setIsPromoting(false);
    }
  }, []);

  const handleAskAssistant = useCallback(async (question: string) => {
    setAssistantError(null);
    setAssistantLoading(true);
    try {
      const response = await askCag(question, "example_region");
      setAssistantAnswer(response);
    } catch (error) {
      setAssistantError(error instanceof Error ? error.message : "Assistant request failed.");
    } finally {
      setAssistantLoading(false);
    }
  }, []);

  const handleCreateFieldAction = useCallback(async () => {
    if (!focusRegion || !fieldActionNote.trim()) return;
    try {
      await createFieldAction(focusRegion.region_id, focusRegion.week, "field_note", fieldActionNote.trim());
      setFieldActionNote("");
      window.location.reload();
    } catch (error) {
      setAssistantError(error instanceof Error ? error.message : "Field action request failed.");
    }
  }, [fieldActionNote, focusRegion]);

  const {
    latestRisk,
    alerts,
    modelStatus,
    modelComparison,
    scoringHealth,
    dataQuality,
    pilotDefinition,
    demoRiskPoints,
    auditLogs,
    fetchedAt,
    apiHealthy,
    error,
  } = data;
  const topRisk = latestRisk[0] ?? null;

  const focusDriversList = focusDrivers
    ? (Object.entries(focusDrivers.drivers) as [string, number][]).sort((a, b) => b[1] - a[1])
    : [];
  const maxDriver = focusDriversList[0]?.[1] ?? 1;

  const mins = Math.floor(countdown / 60);
  const secs = countdown % 60;
  const refreshLabel = `${mins}:${String(secs).padStart(2, "0")}`;

  return (
    <div className="page">
      {/* ── TOPBAR ─────────────────────────────────────────── */}
      <header className="topbar">
        <div className="topbar-brand">
          <span className="brand-icon">◈</span>
          <span className="brand-name">ODSS-WS</span>
          <span className="brand-sep"> // </span>
          <span className="brand-sub">OPERATIONAL DECISION SUPPORT · WATER SECURITY</span>
        </div>
        <div className="topbar-right">
          <div className="sys-status">
            {apiHealthy
              ? <><span className="dot-live" /><span className="sys-label">SYS NOMINAL</span></>
              : <><span className="dot-offline" /><span className="sys-label-bad">API OFFLINE</span></>}
          </div>
          <span className="api-tag">REFRESH {refreshLabel}</span>
          <span className="api-tag">API v0.1</span>
          <span className="topbar-time">{fetchedAt} UTC</span>
        </div>
      </header>

      {!apiHealthy && (
        <div className="status-banner">
          <span>⚠ API UNAVAILABLE</span>
          <span style={{ color: "var(--text)", fontWeight: 400 }}>{error ?? "Dashboard running on cached data."}</span>
        </div>
      )}

      {/* ── STAT BAR ───────────────────────────────────────── */}
      <div className="statbar">
        <div className="stat-cell">
          <div className="stat-label">Highest Risk District</div>
          <div className="stat-value" style={{ color: topRisk ? scoreColor(topRisk.score) : "var(--label)" }}>
            {topRisk?.region_name ?? "—"}
          </div>
          <div className="stat-sub">{topRisk ? `SCORE ${topRisk.score.toFixed(2)}` : "NO DATA"}</div>
        </div>
        <div className="stat-cell">
          <div className="stat-label">Active Alerts</div>
          <div className={`stat-value ${alerts.length > 0 ? "stat-value-red" : "stat-value-green"}`}>
            {alerts.length}
          </div>
          <div className="stat-sub">{alerts.length > 0 ? "REQUIRES OPERATOR REVIEW" : "ALL DISTRICTS NOMINAL"}</div>
        </div>
        <div className="stat-cell">
          <div className="stat-label">Scored Week</div>
          <div className="stat-value stat-value-blue">{topRisk ? shortWeek(topRisk.week) : "—"}</div>
          <div className="stat-sub">DISTRICT · WEEK GRANULARITY</div>
        </div>
        <div className="stat-cell">
          <div className="stat-label">Model Path</div>
          <div className={`stat-value ${modelStatus?.status === "promoted" ? "stat-value-green" : "stat-value-amber"}`}>
            {modelStatus?.status?.toUpperCase() ?? "—"}
          </div>
          <div className="stat-sub">{modelStatus?.model_family?.toUpperCase() ?? "NO MODEL TRAINED"}</div>
        </div>
      </div>

      {/* ── MAIN GRID ──────────────────────────────────────── */}
      <div className="main-grid">
        {/* MAP */}
        <div className="panel">
          <div className="panel-header">
            <span className="panel-title">Tactical Risk Map</span>
            <span className="panel-meta">
              {selectedRegionId
                ? `▶ ${latestRisk.find((r) => r.region_id === selectedRegionId)?.region_name?.toUpperCase() ?? selectedRegionId}`
                : topRisk
                  ? `WK ${topRisk.week} · SELECT DISTRICT`
                  : "AWAITING SCORES"}
            </span>
          </div>

          {latestRisk.length > 0
            ? <TacticalMap
                risks={latestRisk}
                selectedRegionId={selectedRegionId}
                onSelectRegion={setSelectedRegionId}
                apiBaseUrl={API_BASE}
              />
            : <div className="map-loading">RUN SEED TO POPULATE SCORED OUTPUTS</div>}

          <div className="map-footer">
            <div className="legend-row">
              {(["high", "medium", "low"] as const).map((level) => (
                <div className="legend-item" key={level}>
                  <div className={`legend-dot ${level}`} />
                  <span>{level.toUpperCase()}</span>
                </div>
              ))}
            </div>
            <span className="panel-meta">ESRI WORLD IMAGERY · CLICK DISTRICT</span>
          </div>
        </div>

        {/* RIGHT PANEL */}
        <div className="panel">
          <div className="panel-header" style={{ padding: 0 }}>
            {(["alerts", "quality", "model", "ops"] as const).map((tab) => (
              <button
                key={tab}
                onClick={() => setActiveTab(tab)}
                className={`tab-btn${activeTab === tab ? " active" : ""}`}
              >
                {tab === "alerts"
                  ? `ALERTS${alerts.length > 0 ? ` (${alerts.length})` : ""}`
                  : tab === "quality"
                    ? "QUALITY"
                    : tab === "model"
                      ? "MODEL"
                      : "OPS"}
              </button>
            ))}
          </div>

          {activeTab === "alerts" && (
            <div className="alert-list">
              {alerts.length ? alerts.map((alert) => (
                <div className={`alert-row ${alert.severity}`} key={`${alert.region_id}-${alert.week}`}>
                  <div className="alert-row-header">
                    <span className="alert-region">{alert.region_name.toUpperCase()}</span>
                    <span className={`severity-tag ${alert.severity}`}>{alert.severity.toUpperCase()}</span>
                  </div>
                  <div className="alert-score-line">
                    <span className="alert-score-val" style={{ color: scoreColor(alert.score ?? 0) }}>
                      {alert.score != null ? alert.score.toFixed(2) : "—"}
                    </span>
                    <span className="alert-week-tag">{shortWeek(alert.week)}</span>
                  </div>
                  {alert.top_drivers.length > 0 && (
                    <div className="alert-drivers">
                      {alert.top_drivers.map((d, i) => (
                        <span key={d}>
                          <span style={{ color: "var(--label)" }}>{i > 0 ? " · " : ""}</span>
                          {d}
                        </span>
                      ))}
                    </div>
                  )}
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                    <div className="alert-action">→ {alert.recommended_action}</div>
                    <button
                      className="resolve-btn"
                      onClick={() => handleAcknowledgeAlert(alert.region_id, alert.week)}
                    >
                      ACK
                    </button>
                    <button
                      className="resolve-btn"
                      onClick={() => handleResolveAlert(alert.region_id, alert.week)}
                    >
                      RESOLVE
                    </button>
                  </div>
                </div>
              )) : (
                <div className="empty-state">
                  <span className="empty-state-icon">◉</span>
                  NO ACTIVE ALERTS<br />
                  <span style={{ color: "var(--green)", fontSize: "0.65rem" }}>ALL DISTRICTS NOMINAL</span>
                </div>
              )}
            </div>
          )}

          {activeTab === "quality" && <QualityPanel quality={dataQuality} />}

          {activeTab === "model" && (
            modelStatus
              ? (
                <ModelPanel
                  model={modelStatus}
                  comparison={modelComparison}
                  scoringHealth={scoringHealth}
                  onPromote={handlePromoteModel}
                  isPromoting={isPromoting}
                  actionError={modelActionError}
                />
              )
              : (
                <div className="empty-state">
                  <span className="empty-state-icon">◫</span>
                  NO MODEL METADATA<br />RUN TRAINING FIRST
                </div>
              )
          )}

          {activeTab === "ops" && (
            <OpsPanel
              pilot={pilotDefinition}
              demoRiskPoints={demoRiskPoints}
              auditLogs={auditLogs}
              fieldActionNote={fieldActionNote}
              question={assistantQuestion}
              answer={assistantAnswer}
              loading={assistantLoading}
              error={assistantError}
              onQuestionChange={setAssistantQuestion}
              onAsk={handleAskAssistant}
              onFieldActionNoteChange={setFieldActionNote}
              onCreateFieldAction={handleCreateFieldAction}
            />
          )}
        </div>
      </div>

      {/* ── DETAIL GRID ────────────────────────────────────── */}
      <div className="detail-grid">
        {/* FOCUS DISTRICT */}
        <div className="panel">
          <div className="panel-header">
            <span className="panel-title">District Intelligence</span>
            <span className="panel-meta">
              {focusRegion ? focusRegion.region_name.toUpperCase() : "SELECT A DISTRICT"}
            </span>
          </div>
          <div className="focus-body">
            {focusRegion ? (
              <>
                <div className="focus-score-row">
                  <div>
                    <div className="focus-score-big" style={{ color: scoreColor(focusRegion.score) }}>
                      {focusRegion.score.toFixed(2)}
                    </div>
                    <div className="focus-score-sub">RISK SCORE · {shortWeek(focusRegion.week)}</div>
                  </div>
                  <span
                    className={`severity-tag ${focusRegion.risk_level}`}
                    style={{ fontSize: "0.76rem", padding: "0.3rem 0.7rem" }}
                  >
                    {focusRegion.risk_level.toUpperCase()}
                  </span>
                </div>

                {/* Score bar */}
                <div className="score-bar-wrap">
                  <div
                    className="score-bar-fill"
                    style={{
                      width: `${focusRegion.score * 100}%`,
                      background: `linear-gradient(90deg, ${scoreColor(focusRegion.score)}, ${scoreColor(focusRegion.score)}88)`,
                      boxShadow: `0 0 8px ${scoreColor(focusRegion.score)}60`,
                    }}
                  />
                </div>

                <div className="focus-metric-row">
                  <div className="focus-metric">
                    <div className="focus-metric-label">Confidence</div>
                    <div className="focus-metric-value" style={{ textTransform: "capitalize" }}>
                      {focusRegion.confidence}
                    </div>
                  </div>
                  <div className="focus-metric">
                    <div className="focus-metric-label">Active Drivers</div>
                    <div className="focus-metric-value" style={{ color: "var(--blue-hi)" }}>
                      {focusRegion.top_drivers.length}
                    </div>
                  </div>
                </div>

                {focusDriversList.length > 0 && (
                  <>
                    <div className="section-label">Risk Driver Breakdown</div>
                    <div className="driver-list">
                      {focusDriversList.map(([name, value]) => (
                        <div className="driver-row" key={name}>
                          <div className="driver-row-header">
                            <span className="driver-name">{name}</span>
                            <span className="driver-val">{value.toFixed(3)}</span>
                          </div>
                          <div className="driver-track">
                            <div className="driver-fill" style={{ width: `${(value / maxDriver) * 100}%` }} />
                          </div>
                        </div>
                      ))}
                    </div>
                  </>
                )}

                {focusDrivers?.narrative && (
                  <p className="narrative">{focusDrivers.narrative}</p>
                )}
              </>
            ) : (
              <div className="empty-state">
                <span className="empty-state-icon">◎</span>
                CLICK A DISTRICT ON THE MAP<br />TO LOAD ITS RISK PROFILE
              </div>
            )}
          </div>
        </div>

        {/* RISK HISTORY */}
        <div className="panel">
          <div className="panel-header">
            <span className="panel-title">Risk History</span>
            <span className="panel-meta">
              {focusRegion ? focusRegion.region_name.toUpperCase() : "NO DISTRICT SELECTED"}
            </span>
          </div>
          <div className="history-body">
            <RiskHistory history={focusHistory} />
          </div>
        </div>
      </div>
    </div>
  );
}
