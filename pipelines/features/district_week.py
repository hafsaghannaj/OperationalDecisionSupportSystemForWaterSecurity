from __future__ import annotations

import csv
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import date
from hashlib import sha256
from pathlib import Path
from statistics import mean, pstdev
from typing import Mapping

from sqlalchemy import select
from sqlalchemy.orm import Session

from pipelines.ingest.common import create_source_run, file_checksum, sample_data_dir
from services.api.app.db import SessionLocal
from services.api.app.db_models import AdminBoundary, DistrictWeekFeature, DistrictWeekLabel


STATIC_COLUMNS = {
    "region_id",
    "population_total",
    "population_density_km2",
    "wash_access_basic_water_pct",
    "wash_access_basic_sanitation_pct",
}
WEATHER_COLUMNS = {
    "region_id",
    "week_start_date",
    "rainfall_total_mm_7d",
}


@dataclass(slots=True)
class StaticCovariates:
    region_id: str
    population_total: float
    population_density_km2: float
    wash_access_basic_water_pct: float
    wash_access_basic_sanitation_pct: float


@dataclass(slots=True)
class WeatherObservation:
    region_id: str
    week_start_date: date
    rainfall_total_mm_7d: float


@dataclass(slots=True)
class FeatureBuildResult:
    source_run_id: str
    rows_read: int
    rows_inserted: int
    rows_updated: int
    feature_build_version: str

    def as_dict(self) -> dict[str, str | int]:
        return asdict(self)

    def summary(self) -> str:
        return (
            f"district_week_features[{self.feature_build_version}]: "
            f"read {self.rows_read}, inserted {self.rows_inserted}, updated {self.rows_updated}."
        )


def parse_static_covariate_row(row: Mapping[str, str]) -> StaticCovariates:
    missing = STATIC_COLUMNS - set(row)
    if missing:
        raise ValueError(f"Static covariate row is missing required columns: {sorted(missing)}")

    region_id = row["region_id"].strip()
    if not region_id:
        raise ValueError("Static covariate row contains a blank region_id.")

    return StaticCovariates(
        region_id=region_id,
        population_total=float(row["population_total"]),
        population_density_km2=float(row["population_density_km2"]),
        wash_access_basic_water_pct=float(row["wash_access_basic_water_pct"]),
        wash_access_basic_sanitation_pct=float(row["wash_access_basic_sanitation_pct"]),
    )


def parse_weather_row(row: Mapping[str, str]) -> WeatherObservation:
    missing = WEATHER_COLUMNS - set(row)
    if missing:
        raise ValueError(f"Weather row is missing required columns: {sorted(missing)}")

    region_id = row["region_id"].strip()
    week_start_raw = row["week_start_date"].strip()
    rainfall_raw = row["rainfall_total_mm_7d"].strip()
    if not region_id or not week_start_raw or not rainfall_raw:
        raise ValueError("Weather row contains blank required values.")

    return WeatherObservation(
        region_id=region_id,
        week_start_date=date.fromisoformat(week_start_raw),
        rainfall_total_mm_7d=float(rainfall_raw),
    )


def load_static_covariates(csv_path: str | Path) -> dict[str, StaticCovariates]:
    path = Path(csv_path).resolve()
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        return {row.region_id: row for row in (parse_static_covariate_row(record) for record in reader)}


def load_weather(csv_path: str | Path) -> list[WeatherObservation]:
    path = Path(csv_path).resolve()
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        return [parse_weather_row(record) for record in reader]


def weather_map(rows: list[WeatherObservation]) -> dict[tuple[str, date], WeatherObservation]:
    return {(row.region_id, row.week_start_date): row for row in rows}


def rainfall_anomaly_map(rows: list[WeatherObservation]) -> dict[tuple[str, date], float]:
    values_by_region: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        values_by_region[row.region_id].append(row.rainfall_total_mm_7d)

    anomaly_lookup: dict[tuple[str, date], float] = {}
    for row in rows:
        region_values = values_by_region[row.region_id]
        if len(region_values) < 2:
            anomaly_lookup[(row.region_id, row.week_start_date)] = 0.0
            continue

        stdev = pstdev(region_values)
        if stdev == 0:
            anomaly_lookup[(row.region_id, row.week_start_date)] = 0.0
            continue

        anomaly_lookup[(row.region_id, row.week_start_date)] = round(
            (row.rainfall_total_mm_7d - mean(region_values)) / stdev,
            4,
        )

    return anomaly_lookup


def lag_case_count(previous_counts: list[int | None]) -> int | None:
    if not previous_counts:
        return None
    return previous_counts[-1]


def rolling_case_count(previous_counts: list[int | None], window: int = 4) -> int | None:
    window_values = [value for value in previous_counts[-window:] if value is not None]
    if not window_values:
        return None
    return sum(window_values)


def quality_flag(static_row: StaticCovariates | None, weather_row: WeatherObservation | None) -> str:
    if static_row and weather_row:
        return "ok"
    if static_row is None and weather_row is None:
        return "missing_static_and_weather"
    if static_row is None:
        return "missing_static_covariates"
    return "missing_weather"


def _combined_checksum(static_path: Path, weather_path: Path, feature_build_version: str) -> str:
    digest = sha256()
    digest.update(file_checksum(static_path).encode("utf-8"))
    digest.update(file_checksum(weather_path).encode("utf-8"))
    digest.update(feature_build_version.encode("utf-8"))
    return digest.hexdigest()


def _build_with_session(
    session: Session,
    *,
    static_covariates_path: Path,
    weather_path: Path,
    feature_build_version: str,
) -> FeatureBuildResult:
    static_covariates = load_static_covariates(static_covariates_path)
    weather_rows = load_weather(weather_path)
    weather_lookup = weather_map(weather_rows)
    anomaly_lookup = rainfall_anomaly_map(weather_rows)

    label_rows = session.execute(
        select(DistrictWeekLabel, AdminBoundary.country_code, AdminBoundary.admin_level)
        .join(AdminBoundary, AdminBoundary.region_id == DistrictWeekLabel.region_id)
        .order_by(DistrictWeekLabel.region_id, DistrictWeekLabel.week_start_date)
    ).all()

    source_run = create_source_run(
        session,
        source_name="district_week_feature_build",
        upstream_asset_uri=f"{static_covariates_path};{weather_path}",
        record_count=len(label_rows),
        checksum=_combined_checksum(static_covariates_path, weather_path, feature_build_version),
    )

    inserted = 0
    updated = 0
    case_history: dict[str, list[int | None]] = defaultdict(list)

    try:
        for label, country_code, admin_level in label_rows:
            static_row = static_covariates.get(label.region_id)
            weather_row = weather_lookup.get((label.region_id, label.week_start_date))
            existing = session.scalar(
                select(DistrictWeekFeature).where(
                    DistrictWeekFeature.region_id == label.region_id,
                    DistrictWeekFeature.week_start_date == label.week_start_date,
                    DistrictWeekFeature.feature_build_version == feature_build_version,
                )
            )

            values = {
                "country_code": country_code,
                "admin_level": admin_level,
                "source_run_id": source_run.id,
                "feature_build_version": feature_build_version,
                "quality_flag": quality_flag(static_row, weather_row),
                "rainfall_total_mm_7d": weather_row.rainfall_total_mm_7d if weather_row else None,
                "rainfall_anomaly_zscore": anomaly_lookup.get((label.region_id, label.week_start_date)),
                "population_total": static_row.population_total if static_row else None,
                "population_density_km2": static_row.population_density_km2 if static_row else None,
                "wash_access_basic_water_pct": static_row.wash_access_basic_water_pct if static_row else None,
                "wash_access_basic_sanitation_pct": (
                    static_row.wash_access_basic_sanitation_pct if static_row else None
                ),
                "lag_case_count_1w": lag_case_count(case_history[label.region_id]),
                "rolling_case_count_4w": rolling_case_count(case_history[label.region_id]),
            }

            if existing is None:
                session.add(
                    DistrictWeekFeature(
                        region_id=label.region_id,
                        week_start_date=label.week_start_date,
                        **values,
                    )
                )
                inserted += 1
            else:
                for key, value in values.items():
                    setattr(existing, key, value)
                updated += 1

            case_history[label.region_id].append(label.case_count)

        session.commit()
    except Exception:
        session.rollback()
        raise

    return FeatureBuildResult(
        source_run_id=source_run.id,
        rows_read=len(label_rows),
        rows_inserted=inserted,
        rows_updated=updated,
        feature_build_version=feature_build_version,
    )


def build_district_week_features(
    *,
    session: Session | None = None,
    static_covariates_path: str | Path | None = None,
    weather_path: str | Path | None = None,
    feature_build_version: str = "sample-v1",
) -> FeatureBuildResult:
    sample_dir = sample_data_dir()
    resolved_static_path = Path(static_covariates_path or sample_dir / "district_static_covariates.csv").resolve()
    resolved_weather_path = Path(weather_path or sample_dir / "district_week_weather.csv").resolve()

    if session is not None:
        return _build_with_session(
            session,
            static_covariates_path=resolved_static_path,
            weather_path=resolved_weather_path,
            feature_build_version=feature_build_version,
        )

    with SessionLocal() as local_session:
        return _build_with_session(
            local_session,
            static_covariates_path=resolved_static_path,
            weather_path=resolved_weather_path,
            feature_build_version=feature_build_version,
        )
