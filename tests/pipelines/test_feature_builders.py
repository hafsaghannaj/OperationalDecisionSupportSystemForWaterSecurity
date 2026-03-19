from datetime import date

from pipelines.features.district_week import (
    StaticCovariates,
    WeatherObservation,
    lag_case_count,
    parse_static_covariate_row,
    parse_weather_row,
    quality_flag,
    rainfall_anomaly_map,
    rolling_case_count,
)


def test_parse_static_covariate_row() -> None:
    row = parse_static_covariate_row(
        {
            "region_id": "BD-10",
            "population_total": "2680000",
            "population_density_km2": "1180",
            "wash_access_basic_water_pct": "78.0",
            "wash_access_basic_sanitation_pct": "62.0",
        }
    )

    assert row.region_id == "BD-10"
    assert row.population_total == 2680000.0


def test_parse_weather_row() -> None:
    row = parse_weather_row(
        {
            "region_id": "BD-10",
            "week_start_date": "2026-03-09",
            "rainfall_total_mm_7d": "89.0",
        }
    )

    assert row.region_id == "BD-10"
    assert row.week_start_date == date(2026, 3, 9)
    assert row.rainfall_total_mm_7d == 89.0


def test_rainfall_anomaly_map() -> None:
    rows = [
        WeatherObservation(region_id="BD-10", week_start_date=date(2026, 2, 16), rainfall_total_mm_7d=40.0),
        WeatherObservation(region_id="BD-10", week_start_date=date(2026, 2, 23), rainfall_total_mm_7d=50.0),
        WeatherObservation(region_id="BD-10", week_start_date=date(2026, 3, 2), rainfall_total_mm_7d=60.0),
    ]

    anomalies = rainfall_anomaly_map(rows)

    assert anomalies[("BD-10", date(2026, 2, 23))] == 0.0
    assert anomalies[("BD-10", date(2026, 3, 2))] > 1.0


def test_case_lag_helpers() -> None:
    assert lag_case_count([]) is None
    assert lag_case_count([12, 16, 19]) == 19
    assert rolling_case_count([]) is None
    assert rolling_case_count([12, 16, 19]) == 47
    assert rolling_case_count([1, 2, 3, 4, 5]) == 14


def test_quality_flag() -> None:
    static_row = StaticCovariates(
        region_id="BD-10",
        population_total=1.0,
        population_density_km2=2.0,
        wash_access_basic_water_pct=3.0,
        wash_access_basic_sanitation_pct=4.0,
    )
    weather_row = WeatherObservation(
        region_id="BD-10",
        week_start_date=date(2026, 3, 9),
        rainfall_total_mm_7d=89.0,
    )

    assert quality_flag(static_row, weather_row) == "ok"
    assert quality_flag(None, weather_row) == "missing_static_covariates"
    assert quality_flag(static_row, None) == "missing_weather"
    assert quality_flag(None, None) == "missing_static_and_weather"
