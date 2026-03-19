from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from libs.ml.artifacts import latest_model_card_path, model_artifact_dir
from libs.pilot import (
    pilot_geography_label,
    pilot_intended_users_text,
    pilot_outcome_name,
    pilot_prediction_horizon,
)


def model_card_path(model_version: str, output_dir: str | Path | None = None) -> Path:
    return model_artifact_dir(output_dir) / f"{model_version}.md"


def join_values(values: list[str] | None, *, fallback: str) -> str:
    if not values:
        return fallback
    return ", ".join(values)


def known_data_limitations(metadata: Mapping[str, Any]) -> str:
    limitations: list[str] = []
    if str(metadata.get("feature_build_version", "")).startswith("sample-"):
        limitations.append("Current training run uses illustrative sample data rather than a locked pilot feed.")

    non_ok_quality_rows = int(metadata.get("non_ok_quality_rows", 0))
    if non_ok_quality_rows:
        limitations.append(f"{non_ok_quality_rows} training rows carried non-ok feature quality flags.")

    if not limitations:
        limitations.append("Pilot geography, operational thresholds, and partner data limitations still need to be locked.")

    return " ".join(limitations)


def threshold_guidance(metadata: Mapping[str, Any]) -> str:
    policy = metadata.get("promotion_policy") or {}
    min_aucpr = policy.get("min_average_precision")
    min_gain = policy.get("min_average_precision_gain")
    min_logistic_gain = policy.get("min_average_precision_gain_vs_logistic")
    max_brier = policy.get("max_brier_score")
    min_splits = policy.get("min_evaluation_splits")
    thresholds = metadata.get("alert_thresholds") or {}
    threshold_simulation = metadata.get("alert_threshold_simulation") or {}
    medium_threshold = thresholds.get("medium", "n/a")
    high_threshold = thresholds.get("high", "n/a")
    simulation_status = threshold_simulation.get("selection_status", "not recorded")
    high_alert = threshold_simulation.get("high_alert") or {}
    medium_or_higher_alert = threshold_simulation.get("medium_or_higher_alert") or {}
    return (
        f"Promotion requires AUCPR >= {min_aucpr}, AUCPR gain vs persistence >= {min_gain}, "
        f"AUCPR gain vs logistic >= {min_logistic_gain}, Brier score <= {max_brier}, "
        f"and at least {min_splits} forward-chaining split(s). "
        f"Active thresholds are medium >= {medium_threshold} and high >= {high_threshold} [{simulation_status}], "
        f"with validation alert rates {medium_or_higher_alert.get('alert_rate', 'n/a')} for medium+ "
        f"and {high_alert.get('alert_rate', 'n/a')} for high."
    )


def training_freshness_summary(metadata: Mapping[str, Any]) -> str:
    freshness = metadata.get("training_data_freshness") or {}
    if not freshness:
        return "Not recorded"

    latest_week = freshness.get("latest_week", "n/a")
    age_days = freshness.get("age_days", "n/a")
    status = str(freshness.get("status", "unknown"))
    return f"{status} · latest week {latest_week} · age {age_days} day(s)"


def drift_policy_summary(metadata: Mapping[str, Any]) -> str:
    policy = metadata.get("feature_drift_policy") or {}
    if not policy:
        return "Not recorded"

    return (
        f"warning shift >= {policy.get('warn_shift_score', 'n/a')}, "
        f"fail shift >= {policy.get('fail_shift_score', 'n/a')}, "
        f"warning missing delta >= {policy.get('warn_missing_rate_delta', 'n/a')}, "
        f"fail missing delta >= {policy.get('fail_missing_rate_delta', 'n/a')}."
    )


def candidate_comparison(metadata: Mapping[str, Any]) -> str:
    candidate_results = metadata.get("candidate_results") or []
    if not candidate_results:
        return "Not recorded"

    parts: list[str] = []
    for candidate in candidate_results:
        model_family = str(candidate.get("model_family", "unknown"))
        status = str(candidate.get("status", "unknown"))
        if status == "unavailable":
            reason = candidate.get("reason") or "unavailable"
            parts.append(f"{model_family}: unavailable ({reason})")
            continue

        evaluation = candidate.get("evaluation") or {}
        aucpr = evaluation.get("average_precision", "n/a")
        parts.append(f"{model_family}: AUCPR {aucpr} [{status}]")

    return "; ".join(parts)


def render_model_card(metadata: Mapping[str, Any]) -> str:
    evaluation = metadata.get("evaluation") or {}
    training_start = metadata.get("training_start_week", "Not recorded")
    training_end = metadata.get("training_end_week", "Not recorded")
    pilot_geography = metadata.get("pilot_geography", pilot_geography_label())
    outcome_name = metadata.get("outcome_name", pilot_outcome_name())
    prediction_horizon = metadata.get("prediction_horizon", pilot_prediction_horizon())
    intended_users = metadata.get(
        "intended_users",
        pilot_intended_users_text(),
    )

    return "\n".join(
        [
            "# Model Card",
            "",
            "## Model Summary",
            "",
            f"- Model name: {metadata.get('model_family', 'unknown')}",
            f"- Version: {metadata.get('model_version', 'unknown')}",
            "- Owner: OperationalDecisionSupportSystemForWaterSecurity MVP team",
            f"- Training date: {metadata.get('trained_at', 'Not recorded')}",
            f"- Promotion date: {metadata.get('promoted_at') or 'Not promoted'}",
            "",
            "## Intended Use",
            "",
            f"- Pilot geography: {pilot_geography}",
            f"- Outcome: {outcome_name}",
            f"- Prediction horizon: {prediction_horizon}",
            f"- Intended users: {intended_users}",
            "",
            "## Training Data",
            "",
            f"- Time range: {training_start} to {training_end}",
            f"- Label source: {join_values(metadata.get('label_sources'), fallback='Not recorded')}",
            f"- Feature sources: {join_values(metadata.get('feature_sources'), fallback='Not recorded')}",
            f"- Training data freshness: {training_freshness_summary(metadata)}",
            f"- Drift guardrail policy: {drift_policy_summary(metadata)}",
            f"- Known data limitations: {known_data_limitations(metadata)}",
            "",
            "## Evaluation",
            "",
            "- Validation design: Forward-chaining evaluation across weekly district slices.",
            f"- Candidate comparison: {candidate_comparison(metadata)}",
            f"- AUCPR: {evaluation.get('average_precision', 'n/a')}",
            f"- Calibration notes: Brier score {evaluation.get('brier_score', 'n/a')}",
            f"- Threshold guidance: {threshold_guidance(metadata)}",
            "",
            "## Operational Notes",
            "",
            "- Recommended actions for alerts: High risk triggers district review and field verification; medium risk triggers closer monitoring and targeted WASH messaging.",
            "- Human review requirements: Operators should review alerts with recent surveillance context before escalation.",
            "- Failure modes: Label drift, missing weather/static covariates, and unconfirmed pilot thresholds can make scores operationally misleading.",
            "- Monitoring checks: Watch feature quality flags, alert volumes, AUCPR against persistence, data freshness, and feature drift each scoring cycle.",
            "",
        ]
    )


def write_model_card(
    metadata: Mapping[str, Any],
    *,
    output_dir: str | Path | None = None,
    promote: bool = False,
) -> Path:
    artifact_dir = model_artifact_dir(output_dir)
    artifact_dir.mkdir(parents=True, exist_ok=True)
    path = model_card_path(str(metadata["model_version"]), output_dir=output_dir)
    content = render_model_card(metadata)
    path.write_text(content, encoding="utf-8")
    if promote:
        latest_model_card_path(output_dir).write_text(content, encoding="utf-8")
    return path
