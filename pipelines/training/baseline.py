from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any, Callable

from sklearn.base import clone
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score
from sqlalchemy import select
from sqlalchemy.orm import Session

from libs.ml.artifacts import persist_model_artifact
from libs.ml.baselines import (
    MODEL_FEATURE_COLUMNS,
    build_lightgbm_baseline,
    build_logistic_baseline,
    feature_vector,
)
from libs.ml.drift import DEFAULT_FEATURE_DRIFT_POLICY, DriftPolicy, build_feature_profile, resolve_drift_policy
from libs.ml.freshness import (
    DEFAULT_TRAINING_FRESHNESS_POLICY,
    FreshnessCheck,
    FreshnessPolicy,
    assess_latest_week_freshness,
    resolve_freshness_policy,
)
from libs.ml.model_cards import model_card_path as planned_model_card_path, write_model_card
from libs.ml.thresholds import AlertThresholdPolicy, calibrate_alert_thresholds
from services.api.app.db import SessionLocal
from services.api.app.model_registry import upsert_model_training_run
from services.api.app.db_models import DistrictWeekFeature, DistrictWeekLabel


ModelFactory = Callable[[], Any]


def round_metric(value: float | None) -> float | None:
    if value is None:
        return None
    return round(float(value), 4)


@dataclass(slots=True)
class TrainingExample:
    region_id: str
    week_start_date: date
    label_event: bool
    lag_label_event_1w: bool | None
    rainfall_total_mm_7d: float | None
    rainfall_anomaly_zscore: float | None
    population_total: float | None
    population_density_km2: float | None
    wash_access_basic_water_pct: float | None
    wash_access_basic_sanitation_pct: float | None
    lag_case_count_1w: int | None
    rolling_case_count_4w: int | None
    quality_flag: str


@dataclass(slots=True)
class MetricSummary:
    average_precision: float | None
    roc_auc: float | None
    brier_score: float
    positive_rate: float

    def as_dict(self) -> dict[str, float | None]:
        return asdict(self)


@dataclass(slots=True)
class SplitEvaluation:
    train_end_week: str
    test_week: str
    train_rows: int
    test_rows: int
    model: MetricSummary
    persistence: MetricSummary

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(slots=True)
class ModelCandidate:
    model_family: str
    build_estimator: ModelFactory | None
    availability_reason: str | None = None


@dataclass(slots=True)
class CandidateResult:
    model_family: str
    status: str
    evaluation_splits: int
    evaluation: MetricSummary | None
    persistence_baseline: MetricSummary | None
    reason: str | None = None

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(slots=True)
class EvaluatedCandidate:
    model_family: str
    estimator: Any
    split_details: list[SplitEvaluation]
    evaluation: MetricSummary
    persistence_baseline: MetricSummary
    calibration_scores: list[float]
    calibration_labels: list[int]
    candidate_result: CandidateResult


@dataclass(slots=True)
class PromotionPolicy:
    min_average_precision: float = 0.85
    min_average_precision_gain: float = 0.02
    min_average_precision_gain_vs_logistic: float = 0.0
    max_brier_score: float = 0.2
    min_evaluation_splits: int = 2

    def as_dict(self) -> dict[str, float | int]:
        return asdict(self)


@dataclass(slots=True)
class PromotionDecision:
    status: str
    reasons: list[str]
    average_precision_gain: float | None
    average_precision_gain_vs_logistic: float | None

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


DEFAULT_PROMOTION_POLICY = PromotionPolicy()


@dataclass(slots=True)
class BaselineTrainingResult:
    model_version: str
    model_family: str
    feature_build_version: str
    artifact_path: str
    metadata_path: str
    trained_at: str
    training_rows: int
    training_weeks: int
    evaluation_splits: int
    evaluation: MetricSummary
    persistence_baseline: MetricSummary
    promotion_status: str
    promotion_reasons: list[str]
    promoted_at: str | None
    model_card_path: str | None
    training_data_freshness: FreshnessCheck
    candidate_results: list[CandidateResult]

    def as_dict(self) -> dict[str, object]:
        return asdict(self)

    def summary(self) -> str:
        model_ap = "n/a" if self.evaluation.average_precision is None else f"{self.evaluation.average_precision:.4f}"
        persistence_ap = (
            "n/a"
            if self.persistence_baseline.average_precision is None
            else f"{self.persistence_baseline.average_precision:.4f}"
        )
        return (
            f"baseline_training[{self.model_version}]: {self.promotion_status}, winner {self.model_family}, "
            f"trained {self.training_rows} rows across "
            f"{self.training_weeks} week(s), evaluated {self.evaluation_splits} split(s), "
            f"AUCPR {model_ap} vs persistence {persistence_ap}, "
            f"training freshness {self.training_data_freshness.status}."
        )


def labels(rows: list[TrainingExample]) -> list[int]:
    return [1 if row.label_event else 0 for row in rows]


def unique_weeks(rows: list[TrainingExample]) -> list[date]:
    return sorted({row.week_start_date for row in rows})


def model_matrix(rows: list[TrainingExample]) -> list[list[float | int | None]]:
    return [feature_vector(row, feature_columns=MODEL_FEATURE_COLUMNS) for row in rows]


def default_model_candidates() -> list[ModelCandidate]:
    candidates = [ModelCandidate(model_family="logistic_regression", build_estimator=build_logistic_baseline)]

    try:
        build_lightgbm_baseline()
    except Exception as exc:
        candidates.append(
            ModelCandidate(
                model_family="lightgbm",
                build_estimator=None,
                availability_reason=str(exc),
            )
        )
    else:
        candidates.append(ModelCandidate(model_family="lightgbm", build_estimator=build_lightgbm_baseline))

    return candidates


def resolve_feature_build_version(session: Session, feature_build_version: str | None = None) -> str:
    if feature_build_version is not None:
        return feature_build_version

    resolved = session.scalar(
        select(DistrictWeekFeature.feature_build_version)
        .order_by(DistrictWeekFeature.created_at.desc())
        .limit(1)
    )
    if resolved is None:
        raise ValueError("No district_week_features are available for baseline training.")
    return resolved


def load_training_examples(
    session: Session,
    *,
    feature_build_version: str | None = None,
) -> tuple[str, list[TrainingExample], list[str]]:
    resolved_feature_build_version = resolve_feature_build_version(session, feature_build_version)
    rows = session.execute(
        select(DistrictWeekFeature, DistrictWeekLabel)
        .join(
            DistrictWeekLabel,
            (DistrictWeekLabel.region_id == DistrictWeekFeature.region_id)
            & (DistrictWeekLabel.week_start_date == DistrictWeekFeature.week_start_date),
        )
        .where(DistrictWeekFeature.feature_build_version == resolved_feature_build_version)
        .order_by(DistrictWeekFeature.region_id, DistrictWeekFeature.week_start_date)
    ).all()

    if not rows:
        raise ValueError("No joined feature and label rows are available for baseline training.")

    previous_label_event_by_region: dict[str, bool] = {}
    examples: list[TrainingExample] = []
    label_sources = sorted({label.label_source for _feature, label in rows})
    for feature, label in rows:
        examples.append(
            TrainingExample(
                region_id=feature.region_id,
                week_start_date=feature.week_start_date,
                label_event=label.label_event,
                lag_label_event_1w=previous_label_event_by_region.get(feature.region_id),
                rainfall_total_mm_7d=feature.rainfall_total_mm_7d,
                rainfall_anomaly_zscore=feature.rainfall_anomaly_zscore,
                population_total=feature.population_total,
                population_density_km2=feature.population_density_km2,
                wash_access_basic_water_pct=feature.wash_access_basic_water_pct,
                wash_access_basic_sanitation_pct=feature.wash_access_basic_sanitation_pct,
                lag_case_count_1w=feature.lag_case_count_1w,
                rolling_case_count_4w=feature.rolling_case_count_4w,
                quality_flag=feature.quality_flag,
            )
        )
        previous_label_event_by_region[feature.region_id] = label.label_event

    return resolved_feature_build_version, examples, label_sources


def build_forward_chaining_splits(
    rows: list[TrainingExample],
    *,
    min_train_weeks: int = 2,
) -> list[tuple[list[TrainingExample], list[TrainingExample]]]:
    ordered_rows = sorted(rows, key=lambda row: (row.week_start_date, row.region_id))
    weeks = unique_weeks(ordered_rows)
    splits: list[tuple[list[TrainingExample], list[TrainingExample]]] = []

    for index in range(min_train_weeks, len(weeks)):
        train_weeks = set(weeks[:index])
        test_week = weeks[index]
        train_rows = [row for row in ordered_rows if row.week_start_date in train_weeks]
        test_rows = [row for row in ordered_rows if row.week_start_date == test_week]
        if train_rows and test_rows:
            splits.append((train_rows, test_rows))

    return splits


def compute_metric_summary(y_true: list[int], scores: list[float]) -> MetricSummary:
    has_positive = any(y_true)
    has_negative = any(not value for value in y_true)

    average_precision = average_precision_score(y_true, scores) if has_positive else None
    roc_auc = roc_auc_score(y_true, scores) if has_positive and has_negative else None

    return MetricSummary(
        average_precision=round_metric(average_precision),
        roc_auc=round_metric(roc_auc),
        brier_score=round_metric(brier_score_loss(y_true, scores)) or 0.0,
        positive_rate=round_metric(sum(y_true) / len(y_true)) or 0.0,
    )


def aggregate_metric_summaries(summaries: list[MetricSummary]) -> MetricSummary:
    average_precision_values = [summary.average_precision for summary in summaries if summary.average_precision is not None]
    roc_auc_values = [summary.roc_auc for summary in summaries if summary.roc_auc is not None]
    return MetricSummary(
        average_precision=round_metric(mean(average_precision_values)) if average_precision_values else None,
        roc_auc=round_metric(mean(roc_auc_values)) if roc_auc_values else None,
        brier_score=round_metric(mean(summary.brier_score for summary in summaries)) or 0.0,
        positive_rate=round_metric(mean(summary.positive_rate for summary in summaries)) or 0.0,
    )


def evaluate_forward_chaining(
    rows: list[TrainingExample],
    *,
    build_estimator: ModelFactory = build_logistic_baseline,
    min_train_weeks: int = 2,
) -> tuple[list[SplitEvaluation], MetricSummary, MetricSummary, list[float], list[int]]:
    split_details: list[SplitEvaluation] = []
    model_metrics: list[MetricSummary] = []
    persistence_metrics: list[MetricSummary] = []
    calibration_scores: list[float] = []
    calibration_labels: list[int] = []

    for train_rows, test_rows in build_forward_chaining_splits(rows, min_train_weeks=min_train_weeks):
        y_train = labels(train_rows)
        if len(set(y_train)) < 2:
            continue

        estimator = clone(build_estimator())
        estimator.fit(model_matrix(train_rows), y_train)

        y_test = labels(test_rows)
        model_scores = estimator.predict_proba(model_matrix(test_rows))[:, 1].tolist()
        calibration_scores.extend(model_scores)
        calibration_labels.extend(y_test)
        train_prevalence = sum(y_train) / len(y_train)
        persistence_scores = [
            train_prevalence if row.lag_label_event_1w is None else float(row.lag_label_event_1w)
            for row in test_rows
        ]

        model_summary = compute_metric_summary(y_test, model_scores)
        persistence_summary = compute_metric_summary(y_test, persistence_scores)

        split_details.append(
            SplitEvaluation(
                train_end_week=max(row.week_start_date for row in train_rows).isoformat(),
                test_week=test_rows[0].week_start_date.isoformat(),
                train_rows=len(train_rows),
                test_rows=len(test_rows),
                model=model_summary,
                persistence=persistence_summary,
            )
        )
        model_metrics.append(model_summary)
        persistence_metrics.append(persistence_summary)

    if not split_details:
        raise ValueError("Not enough class diversity across forward-chaining splits to evaluate the baseline.")

    return (
        split_details,
        aggregate_metric_summaries(model_metrics),
        aggregate_metric_summaries(persistence_metrics),
        calibration_scores,
        calibration_labels,
    )


def fit_final_model(
    rows: list[TrainingExample],
    *,
    build_estimator: ModelFactory = build_logistic_baseline,
):
    y_train = labels(rows)
    if len(set(y_train)) < 2:
        raise ValueError("Baseline training requires at least two label classes.")

    estimator = build_estimator()
    estimator.fit(model_matrix(rows), y_train)
    return estimator


def candidate_sort_key(candidate: EvaluatedCandidate) -> tuple[float, float, float, int]:
    return (
        candidate.evaluation.average_precision or -1.0,
        -(candidate.evaluation.brier_score),
        candidate.evaluation.roc_auc or -1.0,
        1 if candidate.model_family == "logistic_regression" else 0,
    )


def evaluate_candidates(
    rows: list[TrainingExample],
    *,
    candidate_specs: list[ModelCandidate],
    min_train_weeks: int = 2,
) -> tuple[list[CandidateResult], list[EvaluatedCandidate]]:
    candidate_results: list[CandidateResult] = []
    evaluated_candidates: list[EvaluatedCandidate] = []

    for candidate in candidate_specs:
        if candidate.build_estimator is None:
            candidate_results.append(
                CandidateResult(
                    model_family=candidate.model_family,
                    status="unavailable",
                    evaluation_splits=0,
                    evaluation=None,
                    persistence_baseline=None,
                    reason=candidate.availability_reason,
                )
            )
            continue

        split_details, evaluation, persistence_baseline, calibration_scores, calibration_labels = evaluate_forward_chaining(
            rows,
            build_estimator=candidate.build_estimator,
            min_train_weeks=min_train_weeks,
        )
        estimator = fit_final_model(rows, build_estimator=candidate.build_estimator)
        candidate_result = CandidateResult(
            model_family=candidate.model_family,
            status="evaluated",
            evaluation_splits=len(split_details),
            evaluation=evaluation,
            persistence_baseline=persistence_baseline,
        )
        candidate_results.append(candidate_result)
        evaluated_candidates.append(
            EvaluatedCandidate(
                model_family=candidate.model_family,
                estimator=estimator,
                split_details=split_details,
                evaluation=evaluation,
                persistence_baseline=persistence_baseline,
                calibration_scores=calibration_scores,
                calibration_labels=calibration_labels,
                candidate_result=candidate_result,
            )
        )

    if not evaluated_candidates:
        raise ValueError("No candidate models were available for training.")

    winner = max(evaluated_candidates, key=candidate_sort_key)
    winner.candidate_result.status = "selected"
    return candidate_results, evaluated_candidates


def resolve_promotion_policy(policy: PromotionPolicy | None) -> PromotionPolicy:
    return policy if policy is not None else DEFAULT_PROMOTION_POLICY


def evaluate_promotion(
    evaluation: MetricSummary,
    persistence_baseline: MetricSummary,
    *,
    winner_model_family: str,
    evaluation_splits: int,
    logistic_baseline: MetricSummary | None = None,
    policy: PromotionPolicy | None = None,
) -> PromotionDecision:
    resolved_policy = resolve_promotion_policy(policy)
    reasons: list[str] = []
    model_ap = evaluation.average_precision
    persistence_ap = persistence_baseline.average_precision
    average_precision_gain = None if model_ap is None or persistence_ap is None else round_metric(model_ap - persistence_ap)
    average_precision_gain_vs_logistic = None

    if evaluation_splits < resolved_policy.min_evaluation_splits:
        reasons.append(
            f"Need at least {resolved_policy.min_evaluation_splits} forward-chaining splits; got {evaluation_splits}."
        )

    if model_ap is None:
        reasons.append("Model AUCPR is unavailable.")
    elif model_ap < resolved_policy.min_average_precision:
        reasons.append(
            f"Model AUCPR {model_ap:.4f} is below the minimum {resolved_policy.min_average_precision:.4f}."
        )

    if persistence_ap is None or average_precision_gain is None:
        reasons.append("Persistence AUCPR comparison is unavailable.")
    elif average_precision_gain < resolved_policy.min_average_precision_gain:
        reasons.append(
            f"AUCPR gain vs persistence is {average_precision_gain:.4f}, below the minimum "
            f"{resolved_policy.min_average_precision_gain:.4f}."
        )

    if evaluation.brier_score > resolved_policy.max_brier_score:
        reasons.append(
            f"Brier score {evaluation.brier_score:.4f} exceeds the maximum {resolved_policy.max_brier_score:.4f}."
        )

    if winner_model_family != "logistic_regression":
        logistic_ap = None if logistic_baseline is None else logistic_baseline.average_precision
        average_precision_gain_vs_logistic = (
            None if model_ap is None or logistic_ap is None else round_metric(model_ap - logistic_ap)
        )
        if logistic_ap is None or average_precision_gain_vs_logistic is None:
            reasons.append("Logistic baseline AUCPR comparison is unavailable.")
        elif average_precision_gain_vs_logistic <= resolved_policy.min_average_precision_gain_vs_logistic:
            reasons.append(
                f"AUCPR gain vs logistic is {average_precision_gain_vs_logistic:.4f}, which does not clear the minimum "
                f"{resolved_policy.min_average_precision_gain_vs_logistic:.4f}."
            )

    return PromotionDecision(
        status="eligible" if not reasons else "rejected",
        reasons=reasons,
        average_precision_gain=average_precision_gain,
        average_precision_gain_vs_logistic=average_precision_gain_vs_logistic,
    )


def version_slug(model_family: str) -> str:
    return {
        "logistic_regression": "logreg",
        "lightgbm": "lightgbm",
    }.get(model_family, model_family.replace("_", "-"))


def train_baseline_from_examples(
    rows: list[TrainingExample],
    *,
    feature_build_version: str,
    label_sources: list[str] | None = None,
    output_dir: str | Path | None = None,
    min_train_weeks: int = 2,
    promotion_policy: PromotionPolicy | None = None,
    alert_threshold_policy: AlertThresholdPolicy | None = None,
    freshness_reference_date: date | None = None,
    freshness_policy: FreshnessPolicy | None = None,
    drift_policy: DriftPolicy | None = None,
    candidate_specs: list[ModelCandidate] | None = None,
) -> BaselineTrainingResult:
    if not rows:
        raise ValueError("Cannot train baseline model without training rows.")

    ordered_rows = sorted(rows, key=lambda row: (row.week_start_date, row.region_id))
    training_weeks = unique_weeks(ordered_rows)
    training_data_freshness = assess_latest_week_freshness(
        max(training_weeks),
        scope="training_data",
        reference_date=freshness_reference_date,
        policy=resolve_freshness_policy(freshness_policy, default=DEFAULT_TRAINING_FRESHNESS_POLICY),
    )
    if training_data_freshness.status == "failed":
        raise ValueError(training_data_freshness.message)

    resolved_drift_policy = resolve_drift_policy(drift_policy, default=DEFAULT_FEATURE_DRIFT_POLICY)
    training_feature_profile = build_feature_profile(ordered_rows, feature_columns=MODEL_FEATURE_COLUMNS)
    candidate_results, evaluated_candidates = evaluate_candidates(
        ordered_rows,
        candidate_specs=candidate_specs or default_model_candidates(),
        min_train_weeks=min_train_weeks,
    )
    winner = max(evaluated_candidates, key=candidate_sort_key)
    logistic_candidate = next(
        (candidate for candidate in evaluated_candidates if candidate.model_family == "logistic_regression"),
        None,
    )

    now = datetime.now(timezone.utc).replace(microsecond=0)
    model_version = f"baseline-{version_slug(winner.model_family)}-{now.strftime('%Y%m%dT%H%M%SZ')}"
    alert_threshold_calibration = calibrate_alert_thresholds(
        winner.calibration_scores,
        winner.calibration_labels,
        policy=alert_threshold_policy,
    )
    promotion_decision = evaluate_promotion(
        winner.evaluation,
        winner.persistence_baseline,
        winner_model_family=winner.model_family,
        evaluation_splits=len(winner.split_details),
        logistic_baseline=None if logistic_candidate is None else logistic_candidate.evaluation,
        policy=promotion_policy,
    )
    registry_status = "challenger" if promotion_decision.status == "eligible" else "rejected"
    promoted_at = None
    model_card_path = (
        str(planned_model_card_path(model_version, output_dir=output_dir))
        if promotion_decision.status == "eligible"
        else None
    )
    metadata = {
        "model_version": model_version,
        "model_family": winner.model_family,
        "trained_at": now.isoformat(),
        "promoted_at": promoted_at,
        "feature_build_version": feature_build_version,
        "feature_columns": list(MODEL_FEATURE_COLUMNS),
        "training_rows": len(ordered_rows),
        "training_weeks": len(training_weeks),
        "training_start_week": training_weeks[0].isoformat(),
        "training_end_week": training_weeks[-1].isoformat(),
        "evaluation_splits": len(winner.split_details),
        "evaluation": winner.evaluation.as_dict(),
        "persistence_baseline": winner.persistence_baseline.as_dict(),
        "aucpr_gain_vs_persistence": promotion_decision.average_precision_gain,
        "aucpr_gain_vs_logistic": promotion_decision.average_precision_gain_vs_logistic,
        "promotion_status": promotion_decision.status,
        "promotion_reasons": promotion_decision.reasons,
        "registry_status": registry_status,
        "promotion_policy": resolve_promotion_policy(promotion_policy).as_dict(),
        "alert_threshold_policy": (
            alert_threshold_policy.as_dict() if alert_threshold_policy is not None else AlertThresholdPolicy().as_dict()
        ),
        "training_data_freshness": training_data_freshness.as_dict(),
        "feature_drift_policy": resolved_drift_policy.as_dict(),
        "training_feature_profile": training_feature_profile,
        "alert_thresholds": alert_threshold_calibration.thresholds_as_dict(),
        "alert_threshold_simulation": alert_threshold_calibration.simulation_as_dict(),
        "label_sources": label_sources or [],
        "feature_sources": [f"district_week_features[{feature_build_version}]"],
        "non_ok_quality_rows": sum(1 for row in ordered_rows if row.quality_flag != "ok"),
        "pilot_geography": "Not locked in repo configuration",
        "outcome_name": "District-week outbreak event (`label_event`)",
        "prediction_horizon": "One epidemiological week",
        "intended_users": "Operators and analysts reviewing weekly district alerts before field action.",
        "candidate_results": [candidate.as_dict() for candidate in candidate_results],
        "model_card_path": model_card_path,
        "split_details": [split.as_dict() for split in winner.split_details],
    }
    artifact_path, metadata_path = persist_model_artifact(
        winner.estimator,
        metadata,
        output_dir=output_dir,
        promote=False,
    )
    if promotion_decision.status == "eligible":
        write_model_card(metadata, output_dir=output_dir, promote=False)

    return BaselineTrainingResult(
        model_version=model_version,
        model_family=winner.model_family,
        feature_build_version=feature_build_version,
        artifact_path=str(artifact_path),
        metadata_path=str(metadata_path),
        trained_at=now.isoformat(),
        training_rows=len(ordered_rows),
        training_weeks=len(training_weeks),
        evaluation_splits=len(winner.split_details),
        evaluation=winner.evaluation,
        persistence_baseline=winner.persistence_baseline,
        promotion_status=promotion_decision.status,
        promotion_reasons=promotion_decision.reasons,
        promoted_at=promoted_at,
        model_card_path=model_card_path,
        training_data_freshness=training_data_freshness,
        candidate_results=candidate_results,
    )


def _train_with_session(
    session: Session,
    *,
    feature_build_version: str | None = None,
    output_dir: str | Path | None = None,
    min_train_weeks: int = 2,
    promotion_policy: PromotionPolicy | None = None,
    alert_threshold_policy: AlertThresholdPolicy | None = None,
    freshness_reference_date: date | None = None,
    freshness_policy: FreshnessPolicy | None = None,
    drift_policy: DriftPolicy | None = None,
    candidate_specs: list[ModelCandidate] | None = None,
) -> BaselineTrainingResult:
    resolved_feature_build_version, rows, label_sources = load_training_examples(
        session,
        feature_build_version=feature_build_version,
    )
    return train_baseline_from_examples(
        rows,
        feature_build_version=resolved_feature_build_version,
        label_sources=label_sources,
        output_dir=output_dir,
        min_train_weeks=min_train_weeks,
        promotion_policy=promotion_policy,
        alert_threshold_policy=alert_threshold_policy,
        freshness_reference_date=freshness_reference_date,
        freshness_policy=freshness_policy,
        drift_policy=drift_policy,
        candidate_specs=candidate_specs,
    )


def train_baseline_model(
    *,
    session: Session | None = None,
    feature_build_version: str | None = None,
    output_dir: str | Path | None = None,
    min_train_weeks: int = 2,
    promotion_policy: PromotionPolicy | None = None,
    alert_threshold_policy: AlertThresholdPolicy | None = None,
    freshness_reference_date: date | None = None,
    freshness_policy: FreshnessPolicy | None = None,
    drift_policy: DriftPolicy | None = None,
    candidate_specs: list[ModelCandidate] | None = None,
) -> BaselineTrainingResult:
    if session is not None:
        result = _train_with_session(
            session,
            feature_build_version=feature_build_version,
            output_dir=output_dir,
            min_train_weeks=min_train_weeks,
            promotion_policy=promotion_policy,
            alert_threshold_policy=alert_threshold_policy,
            freshness_reference_date=freshness_reference_date or date.today(),
            freshness_policy=freshness_policy,
            drift_policy=drift_policy,
            candidate_specs=candidate_specs,
        )
        upsert_model_training_run(session, metadata_path=result.metadata_path)
        return result

    with SessionLocal() as local_session:
        result = _train_with_session(
            local_session,
            feature_build_version=feature_build_version,
            output_dir=output_dir,
            min_train_weeks=min_train_weeks,
            promotion_policy=promotion_policy,
            alert_threshold_policy=alert_threshold_policy,
            freshness_reference_date=freshness_reference_date or date.today(),
            freshness_policy=freshness_policy,
            drift_policy=drift_policy,
            candidate_specs=candidate_specs,
        )
        upsert_model_training_run(local_session, metadata_path=result.metadata_path)
        return result


if __name__ == "__main__":
    print(train_baseline_model().summary())
