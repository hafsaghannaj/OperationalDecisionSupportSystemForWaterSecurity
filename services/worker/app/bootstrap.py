from __future__ import annotations

from prefect import flow, get_run_logger

from libs.pilot import write_real_data_manifest
from pipelines.features.district_week import build_district_week_features
from pipelines.ingest.admin_boundaries import ingest_admin_boundaries_from_csv
from pipelines.ingest.common import sample_data_dir
from pipelines.ingest.imerg import ingest_imerg
from pipelines.ingest.labels import (
    ingest_historical_labels_from_csv,
    ingest_real_labels,
    load_label_weeks,
    load_real_label_feed_config,
    validate_real_label_export,
)
from pipelines.scoring.weekly import score_all_weeks
from pipelines.training.baseline import train_baseline_model
from services.api.app.db import SessionLocal

SAMPLE_LABEL_SOURCE = "dhs_proxy_surveillance"


@flow(name="water-security-bootstrap-dev-data")
def bootstrap_dev_data_flow() -> dict[str, object]:
    logger = get_run_logger()
    sample_dir = sample_data_dir()

    with SessionLocal() as session:
        boundaries = ingest_admin_boundaries_from_csv(
            session,
            sample_dir / "admin_boundaries.csv",
            source_name="sample_admin_boundaries",
        )
    logger.info(boundaries.summary())

    with SessionLocal() as session:
        labels = ingest_historical_labels_from_csv(
            session,
            sample_dir / "district_week_labels.csv",
            source_name="sample_historical_labels",
        )
    logger.info(labels.summary())

    with SessionLocal() as session:
        features = build_district_week_features(
            session=session,
            static_covariates_path=sample_dir / "district_static_covariates.csv",
            weather_path=sample_dir / "district_week_weather.csv",
            feature_build_version="sample-v1",
            label_source=SAMPLE_LABEL_SOURCE,
        )
    logger.info(features.summary())

    with SessionLocal() as session:
        training = train_baseline_model(
            session=session,
            feature_build_version=features.feature_build_version,
            label_source=SAMPLE_LABEL_SOURCE,
        )
    logger.info(training.summary())

    with SessionLocal() as session:
        scores = score_all_weeks(
            session=session,
            model_version=training.model_version,
            feature_build_version=features.feature_build_version,
        )
    logger.info(scores.summary())

    return {
        "boundaries": boundaries.as_dict(),
        "labels": labels.as_dict(),
        "features": features.as_dict(),
        "training": training.as_dict(),
        "scores": scores.as_dict(),
    }


@flow(name="water-security-bootstrap-real-data")
def bootstrap_real_data_flow() -> dict[str, object]:
    """Bootstrap pipeline using real GeoBoundaries + OCHA + DHS data."""
    from pipelines.ingest.geoboundaries import ingest_bgd_boundaries
    from pipelines.ingest.ocha_dhs import fetch_bgd_static_covariates

    logger = get_run_logger()
    sample_dir = sample_data_dir()
    real_label_config = load_real_label_feed_config()
    if real_label_config is None:
        raise ValueError("Real bootstrap requires ODSSWS_REAL_LABELS_MODE to be configured.")
    manifest_path = write_real_data_manifest()
    logger.info("Pilot real-data manifest written to %s", manifest_path)

    with SessionLocal() as session:
        boundaries = ingest_bgd_boundaries(session)
    logger.info(boundaries.summary())

    real_static_path = fetch_bgd_static_covariates()
    logger.info("Real static covariates written to %s", real_static_path)

    with SessionLocal() as session:
        validation = validate_real_label_export(session, config=real_label_config, write_normalized=True)
    logger.info(
        "Real label validation: rows=%s valid=%s invalid=%s aggregated=%s regions=%s weeks=%s..%s",
        validation.rows_read,
        validation.valid_rows,
        validation.invalid_rows,
        validation.aggregated_rows,
        validation.distinct_regions,
        validation.earliest_week,
        validation.latest_week,
    )
    if validation.invalid_rows:
        first_issue = validation.issues[0]
        raise ValueError(
            f"Real label validation failed at row {first_issue.row_number}: {first_issue.message}"
        )

    with SessionLocal() as session:
        labels = ingest_real_labels(
            session,
            config=real_label_config,
            source_name="dghs_dhis2_labels",
        )
    logger.info(labels.summary())

    with SessionLocal() as session:
        label_weeks = load_label_weeks(session, label_source=real_label_config.label_source)
        real_weather_path = ingest_imerg(session=session, week_starts=label_weeks)
    logger.info("Real weather path written to %s", real_weather_path)

    with SessionLocal() as session:
        features = build_district_week_features(
            session=session,
            static_covariates_path=real_static_path,
            weather_path=real_weather_path,
            feature_build_version="real-v1",
            label_source=real_label_config.label_source,
        )
    logger.info(features.summary())

    with SessionLocal() as session:
        training = train_baseline_model(
            session=session,
            feature_build_version=features.feature_build_version,
            label_source=real_label_config.label_source,
        )
    logger.info(training.summary())

    with SessionLocal() as session:
        scores = score_all_weeks(
            session=session,
            model_version=training.model_version,
            feature_build_version=features.feature_build_version,
        )
    logger.info(scores.summary())

    return {
        "manifest_path": str(manifest_path),
        "label_validation": validation.as_dict(),
        "boundaries": boundaries.as_dict(),
        "labels": labels.as_dict(),
        "features": features.as_dict(),
        "training": training.as_dict(),
        "scores": scores.as_dict(),
    }


if __name__ == "__main__":
    print("Available flows:")
    print("  bootstrap_dev_data_flow()  — sample CSV data (dev/test)")
    print("  bootstrap_real_data_flow() — real GeoBoundaries + OCHA + DHS data")
    print()
    print(bootstrap_dev_data_flow())
