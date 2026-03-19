from __future__ import annotations

from prefect import flow, get_run_logger

from libs.pilot import write_real_data_manifest
from pipelines.features.district_week import build_district_week_features
from pipelines.ingest.admin_boundaries import ingest_admin_boundaries_from_csv
from pipelines.ingest.common import sample_data_dir
from pipelines.ingest.labels import ingest_historical_labels_from_csv, ingest_real_labels
from pipelines.scoring.weekly import score_all_weeks
from pipelines.training.baseline import train_baseline_model
from services.api.app.db import SessionLocal


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
        )
    logger.info(features.summary())

    with SessionLocal() as session:
        training = train_baseline_model(
            session=session,
            feature_build_version=features.feature_build_version,
        )
    logger.info(training.summary())

    with SessionLocal() as session:
        scores = score_all_weeks(session=session)
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
    manifest_path = write_real_data_manifest()
    logger.info("Pilot real-data manifest written to %s", manifest_path)

    with SessionLocal() as session:
        boundaries = ingest_bgd_boundaries(session)
    logger.info(boundaries.summary())

    real_static_path = fetch_bgd_static_covariates()
    logger.info("Real static covariates written to %s", real_static_path)

    with SessionLocal() as session:
        labels = ingest_real_labels(
            session,
            source_name="dghs_dhis2_labels",
        )
    logger.info(labels.summary())

    with SessionLocal() as session:
        features = build_district_week_features(
            session=session,
            static_covariates_path=real_static_path,
            weather_path=sample_dir / "district_week_weather.csv",
            feature_build_version="real-v1",
        )
    logger.info(features.summary())

    with SessionLocal() as session:
        training = train_baseline_model(
            session=session,
            feature_build_version=features.feature_build_version,
        )
    logger.info(training.summary())

    with SessionLocal() as session:
        scores = score_all_weeks(session=session)
    logger.info(scores.summary())

    return {
        "manifest_path": str(manifest_path),
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
