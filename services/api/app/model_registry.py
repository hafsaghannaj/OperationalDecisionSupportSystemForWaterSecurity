from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from libs.ml.artifacts import latest_metadata_path
from libs.ml.model_cards import write_model_card
from libs.schemas.risk import (
    FreshnessStatus,
    ModelComparison,
    ModelMetricSummary,
    ModelPromotionResponse,
    ModelRunSummary,
)
from services.api.app.db_models import ModelTrainingRun


def parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value)


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


def read_run_metadata(metadata_path: str | Path) -> dict[str, Any]:
    return json.loads(Path(metadata_path).resolve().read_text(encoding="utf-8"))


def write_run_metadata(metadata_path: str | Path, metadata: Mapping[str, Any]) -> None:
    payload = json.dumps(dict(metadata), indent=2, sort_keys=True)
    Path(metadata_path).resolve().write_text(f"{payload}\n", encoding="utf-8")


def build_model_run_summary(record: ModelTrainingRun) -> ModelRunSummary:
    metadata = record.run_metadata or {}
    thresholds = metadata.get("alert_thresholds") or None
    normalized_thresholds = None
    if thresholds:
        normalized_thresholds = {
            str(key): float(value)
            for key, value in thresholds.items()
            if value is not None
        }

    return ModelRunSummary(
        model_version=record.model_version,
        model_family=record.model_family,
        registry_status=record.registry_status,
        promotion_status=record.promotion_status,
        trained_at=record.trained_at.isoformat(),
        promoted_at=None if record.promoted_at is None else record.promoted_at.isoformat(),
        feature_build_version=record.feature_build_version,
        training_rows=record.training_rows,
        training_weeks=record.training_weeks,
        evaluation_splits=record.evaluation_splits,
        evaluation=build_metric_summary(metadata.get("evaluation")),
        persistence_baseline=build_metric_summary(metadata.get("persistence_baseline")),
        training_data_freshness=build_freshness_status(metadata.get("training_data_freshness")),
        alert_thresholds=normalized_thresholds,
        promotion_reasons=[str(reason) for reason in metadata.get("promotion_reasons", [])],
        model_card_path=record.model_card_path,
    )


def upsert_model_training_run(session: Session, *, metadata_path: str | Path) -> ModelTrainingRun:
    metadata = read_run_metadata(metadata_path)
    model_version = str(metadata["model_version"])
    record = session.scalar(select(ModelTrainingRun).where(ModelTrainingRun.model_version == model_version))

    trained_at = parse_datetime(metadata.get("trained_at")) or datetime.now(timezone.utc).replace(microsecond=0)
    promoted_at = parse_datetime(metadata.get("promoted_at"))
    promotion_status = str(metadata.get("promotion_status", "rejected"))
    registry_status = str(
        metadata.get("registry_status")
        or ("challenger" if promotion_status == "eligible" else "rejected")
    )

    payload = {
        "model_family": str(metadata.get("model_family", "unknown")),
        "registry_status": registry_status,
        "promotion_status": promotion_status,
        "feature_build_version": metadata.get("feature_build_version"),
        "artifact_path": str(metadata["model_path"]),
        "metadata_path": str(Path(metadata_path).resolve()),
        "model_card_path": metadata.get("model_card_path"),
        "training_rows": int(metadata.get("training_rows", 0)),
        "training_weeks": int(metadata.get("training_weeks", 0)),
        "evaluation_splits": int(metadata.get("evaluation_splits", 0)),
        "trained_at": trained_at,
        "promoted_at": promoted_at,
        "run_metadata": metadata,
    }

    if record is None:
        record = ModelTrainingRun(model_version=model_version, **payload)
        session.add(record)
    else:
        for key, value in payload.items():
            setattr(record, key, value)

    session.commit()
    session.refresh(record)
    return record


def load_model_comparison(session: Session, *, recent_limit: int = 5) -> ModelComparison:
    active_model = session.scalar(
        select(ModelTrainingRun)
        .where(ModelTrainingRun.registry_status == "active")
        .order_by(desc(ModelTrainingRun.promoted_at), desc(ModelTrainingRun.trained_at))
        .limit(1)
    )
    challenger_model = session.scalar(
        select(ModelTrainingRun)
        .where(ModelTrainingRun.registry_status == "challenger")
        .order_by(desc(ModelTrainingRun.trained_at))
        .limit(1)
    )
    recent_runs = session.scalars(
        select(ModelTrainingRun)
        .order_by(desc(ModelTrainingRun.trained_at))
        .limit(recent_limit)
    ).all()

    return ModelComparison(
        active_model=None if active_model is None else build_model_run_summary(active_model),
        challenger_model=None if challenger_model is None else build_model_run_summary(challenger_model),
        recent_runs=[build_model_run_summary(record) for record in recent_runs],
    )


def promote_model_run(session: Session, model_version: str) -> ModelPromotionResponse:
    target = session.scalar(select(ModelTrainingRun).where(ModelTrainingRun.model_version == model_version))
    if target is None:
        raise LookupError(f"Model run '{model_version}' was not found.")

    if target.registry_status == "active":
        return ModelPromotionResponse(
            model_version=model_version,
            status="already_active",
            message="Model is already the active champion.",
            previous_active_model_version=model_version,
        )

    if target.promotion_status != "eligible":
        raise ValueError(f"Model run '{model_version}' is not promotion-eligible.")

    prior_active_runs = session.scalars(
        select(ModelTrainingRun)
        .where(ModelTrainingRun.registry_status == "active")
        .order_by(desc(ModelTrainingRun.promoted_at), desc(ModelTrainingRun.trained_at))
    ).all()
    previous_active_model_version = prior_active_runs[0].model_version if prior_active_runs else None

    for record in prior_active_runs:
        record.registry_status = "archived"
        archived_metadata = dict(record.run_metadata or {})
        archived_metadata["registry_status"] = "archived"
        record.run_metadata = archived_metadata
        write_run_metadata(record.metadata_path, archived_metadata)

    promoted_at = datetime.now(timezone.utc).replace(microsecond=0)
    target.registry_status = "active"
    target.promoted_at = promoted_at

    metadata = dict(target.run_metadata or read_run_metadata(target.metadata_path))
    metadata["registry_status"] = "active"
    metadata["promoted_at"] = promoted_at.isoformat()
    artifact_dir = Path(target.metadata_path).resolve().parent
    card_path = write_model_card(metadata, output_dir=artifact_dir, promote=True)
    metadata["model_card_path"] = str(card_path)

    target.model_card_path = str(card_path)
    target.run_metadata = metadata

    write_run_metadata(target.metadata_path, metadata)
    latest_metadata_path(artifact_dir).write_text(
        f"{json.dumps(metadata, indent=2, sort_keys=True)}\n",
        encoding="utf-8",
    )

    session.commit()

    return ModelPromotionResponse(
        model_version=model_version,
        status="promoted",
        message="Model has been promoted to the active champion.",
        previous_active_model_version=previous_active_model_version,
    )
