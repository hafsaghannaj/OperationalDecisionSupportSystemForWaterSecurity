from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from libs.ml.artifacts import load_promoted_model
from libs.schemas.risk import DriftStatus, FeatureDriftDetail, FreshnessStatus, ModelCardDocument, ModelMetricSummary, ModelStatus
from pipelines.scoring.weekly import MODEL_VERSION as HEURISTIC_MODEL_VERSION, load_scoring_feature_drift
from services.api.app.db import SessionLocal


def build_metric_summary(payload: Mapping[str, Any] | None) -> ModelMetricSummary | None:
    if not payload:
        return None

    return ModelMetricSummary(
        average_precision=payload.get("average_precision"),
        roc_auc=payload.get("roc_auc"),
        brier_score=float(payload.get("brier_score", 0.0)),
        positive_rate=float(payload.get("positive_rate", 0.0)),
    )


def build_freshness_status(payload: Mapping[str, Any] | None) -> FreshnessStatus | None:
    if not payload:
        return None

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


def build_drift_status(payload: Mapping[str, Any] | None) -> DriftStatus | None:
    if not payload:
        return None

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


def load_model_status() -> ModelStatus:
    promoted_model = load_promoted_model()
    if promoted_model is None:
        return ModelStatus(
            status="fallback",
            model_version=HEURISTIC_MODEL_VERSION,
            model_family="heuristic",
            trained_at=None,
            promoted_at=None,
            feature_build_version=None,
            training_rows=None,
            training_weeks=None,
            evaluation_splits=None,
            evaluation=None,
            persistence_baseline=None,
            model_card_path=None,
            training_data_freshness=None,
            scoring_feature_drift=None,
        )

    metadata = promoted_model.metadata
    scoring_feature_drift = None
    try:
        with SessionLocal() as session:
            scoring_feature_drift = load_scoring_feature_drift(
                session,
                promoted_model=promoted_model,
                feature_build_version=metadata.get("feature_build_version"),
                latest_only=True,
            )
    except Exception:
        scoring_feature_drift = None

    return ModelStatus(
        status="promoted",
        model_version=str(metadata["model_version"]),
        model_family=str(metadata.get("model_family", "unknown")),
        trained_at=metadata.get("trained_at"),
        promoted_at=metadata.get("promoted_at"),
        feature_build_version=metadata.get("feature_build_version"),
        training_rows=metadata.get("training_rows"),
        training_weeks=metadata.get("training_weeks"),
        evaluation_splits=metadata.get("evaluation_splits"),
        evaluation=build_metric_summary(metadata.get("evaluation")),
        persistence_baseline=build_metric_summary(metadata.get("persistence_baseline")),
        model_card_path=metadata.get("model_card_path"),
        training_data_freshness=build_freshness_status(metadata.get("training_data_freshness")),
        scoring_feature_drift=None if scoring_feature_drift is None else build_drift_status(scoring_feature_drift.as_dict()),
    )


def load_model_card() -> ModelCardDocument | None:
    promoted_model = load_promoted_model()
    if promoted_model is None:
        return None

    metadata = promoted_model.metadata
    model_card_path = metadata.get("model_card_path")
    if not model_card_path:
        return None

    card_path = Path(str(model_card_path)).resolve()
    if not card_path.exists():
        return None

    return ModelCardDocument(
        model_version=str(metadata["model_version"]),
        promoted_at=metadata.get("promoted_at"),
        content=card_path.read_text(encoding="utf-8"),
    )
