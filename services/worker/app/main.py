from __future__ import annotations

from pathlib import Path

from prefect import flow, get_run_logger
from prefect.schedules import Cron

from pipelines.features.district_week import build_district_week_features
from pipelines.ingest.imerg import OUTPUT_DIR, ingest_imerg
from pipelines.scoring.weekly import score_latest_week

IMERG_LATEST = OUTPUT_DIR / "latest.csv"
SAMPLE_WEATHER = Path(__file__).parents[3] / "sample_data" / "district_week_weather.csv"


@flow(name="water-security-weekly-score")
def weekly_score_flow() -> dict[str, str]:
    logger = get_run_logger()
    logger.info("Starting OperationalDecisionSupportSystemForWaterSecurity weekly score flow.")

    ingest_summary = ingest_imerg()
    logger.info("IMERG ingest: %s", ingest_summary)

    weather_path = IMERG_LATEST if IMERG_LATEST.exists() else SAMPLE_WEATHER
    feature_result = build_district_week_features(
        weather_path=weather_path,
        feature_build_version="imerg-v1",
    )
    feature_summary = feature_result.summary()
    logger.info("Features: %s", feature_summary)

    scoring_result = score_latest_week()
    scoring_summary = scoring_result.summary()
    logger.info("Scoring: %s", scoring_summary)

    logger.info("Weekly score flow completed.")
    return {
        "ingest": ingest_summary,
        "features": feature_summary,
        "scoring": scoring_summary,
    }


if __name__ == "__main__":
    weekly_score_flow.serve(
        name="weekly-score-deployment",
        schedules=[Cron("0 6 * * 1", timezone="UTC")],
    )
