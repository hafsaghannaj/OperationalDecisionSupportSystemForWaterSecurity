from __future__ import annotations

import csv
import hashlib
import json
import re
from pathlib import Path

from libs.pilot import load_pilot_definition
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.metrics import mean_absolute_error, r2_score


REPO_ROOT = Path(__file__).resolve().parents[2]
RESULTS_DIR = REPO_ROOT / "results"
DATA_DIR = REPO_ROOT / "data"
SITE_PATH = REPO_ROOT / "index.html"
SAMPLE_DATA_DIR = REPO_ROOT / "sample_data"
LIVE_STATIC_PATH = DATA_DIR / "covariates" / "bgd_district_static_covariates.csv"
LIVE_WEATHER_PATH = DATA_DIR / "imerg" / "latest.csv"


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def parse_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "t", "yes", "y"}


def build_regressor():
    try:
        from xgboost import XGBRegressor  # type: ignore

        return XGBRegressor(
            n_estimators=80,
            max_depth=4,
            learning_rate=0.08,
            subsample=0.9,
            colsample_bytree=0.9,
            random_state=42,
        ), "XGBoost"
    except Exception:
        return GradientBoostingRegressor(random_state=42), "GradientBoostingRegressor"


def parse_centroid_from_wkt(wkt: str) -> tuple[float, float]:
    values = [float(value) for value in re.findall(r"-?\d+(?:\.\d+)?", wkt)]
    longitudes = values[0::2]
    latitudes = values[1::2]
    return (sum(latitudes) / len(latitudes), sum(longitudes) / len(longitudes))


def fallback_coords(region_id: str) -> tuple[float, float]:
    digest = hashlib.sha256(region_id.encode("utf-8")).digest()
    lat = 20.8 + (digest[0] / 255.0) * 5.2
    lon = 88.0 + (digest[1] / 255.0) * 4.0
    return round(lat, 5), round(lon, 5)


def boundary_reference() -> tuple[dict[str, str], dict[str, tuple[float, float]]]:
    names: dict[str, str] = {}
    coords: dict[str, tuple[float, float]] = {}
    for row in read_csv_rows(SAMPLE_DATA_DIR / "admin_boundaries.csv"):
        region_id = row["region_id"]
        names[region_id] = row["name"]
        coords[region_id] = parse_centroid_from_wkt(row["geometry_wkt"])
    return names, coords


def rainfall_anomaly_lookup(weather_rows: list[dict[str, str]]) -> dict[tuple[str, str], float]:
    by_region: dict[str, list[float]] = {}
    for row in weather_rows:
        by_region.setdefault(row["region_id"], []).append(float(row["rainfall_total_mm_7d"]))

    anomalies: dict[tuple[str, str], float] = {}
    for row in weather_rows:
        series = by_region[row["region_id"]]
        rainfall = float(row["rainfall_total_mm_7d"])
        mean_rainfall = sum(series) / len(series)
        if len(series) == 1:
            anomalies[(row["region_id"], row["week_start_date"])] = 0.0
            continue
        variance = sum((value - mean_rainfall) ** 2 for value in series) / len(series)
        stddev = variance ** 0.5
        anomalies[(row["region_id"], row["week_start_date"])] = 0.0 if stddev == 0 else (rainfall - mean_rainfall) / stddev
    return anomalies


def build_feature_row(
    *,
    rainfall_mm_7d: float,
    population_density_km2: float,
    wash_access_basic_sanitation_pct: float,
    wash_access_basic_water_pct: float,
    rainfall_anomaly_zscore: float,
) -> dict[str, float]:
    flood_proxy = clamp(rainfall_mm_7d / 20.0, 0.0, 1.0)
    temperature_c = round(27.0 + flood_proxy * 4.2 - rainfall_anomaly_zscore * 0.4, 2)
    surface_water_index = round(clamp(0.18 + flood_proxy * 0.62 + max(rainfall_anomaly_zscore, 0.0) * 0.08, 0.0, 1.0), 3)
    return {
        "rainfall_mm_7d": round(rainfall_mm_7d, 2),
        "flood_proxy": round(flood_proxy, 3),
        "sanitation_access_pct": round(wash_access_basic_sanitation_pct, 2),
        "population_density_km2": round(population_density_km2, 2),
        "temperature_c": temperature_c,
        "surface_water_index": surface_water_index,
        "wash_access_basic_water_pct": round(wash_access_basic_water_pct, 2),
        "rainfall_anomaly_zscore": round(rainfall_anomaly_zscore, 3),
    }


def training_rows() -> list[dict[str, object]]:
    static_rows = {row["region_id"]: row for row in read_csv_rows(SAMPLE_DATA_DIR / "district_static_covariates.csv")}
    weather_rows = read_csv_rows(SAMPLE_DATA_DIR / "district_week_weather.csv")
    label_rows = {(row["region_id"], row["week_start_date"]): row for row in read_csv_rows(SAMPLE_DATA_DIR / "district_week_labels.csv")}
    names, coords = boundary_reference()
    anomalies = rainfall_anomaly_lookup(weather_rows)

    rows: list[dict[str, object]] = []
    for weather in weather_rows:
        region_id = weather["region_id"]
        week_start_date = weather["week_start_date"]
        static_row = static_rows[region_id]
        label_row = label_rows[(region_id, week_start_date)]
        rainfall_mm_7d = float(weather["rainfall_total_mm_7d"])
        sanitation = float(static_row["wash_access_basic_sanitation_pct"])
        water = float(static_row["wash_access_basic_water_pct"])
        density = float(static_row["population_density_km2"])
        anomaly = anomalies[(region_id, week_start_date)]
        feature_row = build_feature_row(
            rainfall_mm_7d=rainfall_mm_7d,
            population_density_km2=density,
            wash_access_basic_sanitation_pct=sanitation,
            wash_access_basic_water_pct=water,
            rainfall_anomaly_zscore=anomaly,
        )
        case_count = int(label_row["case_count"])
        label_event = parse_bool(label_row["label_event"])
        risk_target = clamp(
            8.0
            + rainfall_mm_7d * 1.9
            + max(0.0, 84.0 - sanitation) * 0.75
            + max(0.0, density - 400.0) / 180.0
            + max(0.0, 95.0 - water) * 0.35
            + max(0.0, anomaly) * 6.0
            + (8.0 if label_event else 0.0),
            1.0,
            100.0,
        )
        latitude, longitude = coords.get(region_id, fallback_coords(region_id))
        rows.append(
            {
                "region_id": region_id,
                "location_label": names.get(region_id, region_id),
                "latitude": round(latitude, 5),
                "longitude": round(longitude, 5),
                "target_date": week_start_date,
                **feature_row,
                "risk_score": round(risk_target, 2),
                "label_event": label_event,
                "case_count": case_count,
                "label_source": label_row["label_source"],
            }
        )
    return rows


def select_scoring_inputs() -> tuple[str, Path, Path]:
    if LIVE_STATIC_PATH.exists() and LIVE_WEATHER_PATH.exists():
        return ("live_covariates", LIVE_STATIC_PATH, LIVE_WEATHER_PATH)
    return (
        "fixture_covariates",
        SAMPLE_DATA_DIR / "district_static_covariates.csv",
        SAMPLE_DATA_DIR / "district_week_weather.csv",
    )


def latest_week_rows(weather_rows: list[dict[str, str]]) -> list[dict[str, str]]:
    latest_week = max(row["week_start_date"] for row in weather_rows)
    return [row for row in weather_rows if row["week_start_date"] == latest_week]


def driver_summary(rainfall_mm_7d: float, sanitation: float, density: float) -> str:
    drivers: list[tuple[float, str]] = [
        (rainfall_mm_7d, f"rainfall {rainfall_mm_7d:.1f} mm"),
        (100.0 - sanitation, f"sanitation gap {100.0 - sanitation:.1f} pts"),
        (density / 40.0, f"density {density:.0f}/km2"),
    ]
    ranked = [label for _score, label in sorted(drivers, reverse=True)[:2]]
    return " + ".join(ranked)


def scoring_rows() -> tuple[str, list[dict[str, object]]]:
    source_mode, static_path, weather_path = select_scoring_inputs()
    static_rows = {row["region_id"]: row for row in read_csv_rows(static_path)}
    weather_rows = latest_week_rows(read_csv_rows(weather_path))
    anomalies = rainfall_anomaly_lookup(read_csv_rows(weather_path))
    names, coords = boundary_reference()

    rows: list[dict[str, object]] = []
    for weather in weather_rows:
        region_id = weather["region_id"]
        static_row = static_rows.get(region_id)
        if static_row is None:
            continue
        rainfall_mm_7d = float(weather["rainfall_total_mm_7d"])
        sanitation = float(static_row["wash_access_basic_sanitation_pct"] or 0.0)
        water = float(static_row["wash_access_basic_water_pct"] or 0.0)
        density = float(static_row["population_density_km2"])
        anomaly = anomalies.get((region_id, weather["week_start_date"]), 0.0)
        feature_row = build_feature_row(
            rainfall_mm_7d=rainfall_mm_7d,
            population_density_km2=density,
            wash_access_basic_sanitation_pct=sanitation,
            wash_access_basic_water_pct=water,
            rainfall_anomaly_zscore=anomaly,
        )
        latitude, longitude = coords.get(region_id, fallback_coords(region_id))
        rows.append(
            {
                "region_id": region_id,
                "location_label": names.get(region_id, region_id),
                "latitude": round(latitude, 5),
                "longitude": round(longitude, 5),
                "target_date": weather["week_start_date"],
                **feature_row,
                "driver_summary": driver_summary(rainfall_mm_7d, sanitation, density),
            }
        )

    return source_mode, rows


def model_features(rows: list[dict[str, object]]) -> list[list[float]]:
    return [
        [
            float(row["rainfall_mm_7d"]),
            float(row["flood_proxy"]),
            float(row["sanitation_access_pct"]),
            float(row["population_density_km2"]),
            float(row["temperature_c"]),
            float(row["surface_water_index"]),
        ]
        for row in rows
    ]


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    if not rows:
        raise ValueError("rows must not be empty")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def render_map_html(title: str, subtitle: str, points: list[dict[str, object]]) -> str:
    payload = json.dumps(points)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title}</title>
  <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
  <style>
    body {{
      margin: 0;
      font-family: "IBM Plex Sans", "Segoe UI", sans-serif;
      background: linear-gradient(180deg, #081726 0%, #041018 100%);
      color: #d8ebf6;
    }}
    .hero {{ padding: 24px 24px 12px; }}
    h1 {{ margin: 0 0 6px; font-size: 1.8rem; }}
    p {{ margin: 0; color: #9fc0d4; max-width: 60rem; }}
    #map {{
      height: 72vh;
      margin: 12px 24px 24px;
      border: 1px solid rgba(111, 184, 225, 0.25);
      border-radius: 18px;
      overflow: hidden;
      box-shadow: 0 24px 80px rgba(0, 0, 0, 0.3);
    }}
    .legend {{
      margin: 0 24px 24px;
      display: flex;
      gap: 16px;
      flex-wrap: wrap;
      color: #b7d5e8;
      font-size: 0.92rem;
    }}
    .legend span::before {{
      content: "";
      display: inline-block;
      width: 10px;
      height: 10px;
      margin-right: 8px;
      border-radius: 50%;
      vertical-align: middle;
    }}
    .low::before {{ background: #22c55e; }}
    .medium::before {{ background: #f59e0b; }}
    .high::before {{ background: #ef4444; }}
  </style>
</head>
<body>
  <section class="hero">
    <h1>{title}</h1>
    <p>{subtitle}</p>
  </section>
  <div id="map"></div>
  <div class="legend">
    <span class="low">Low risk under 40</span>
    <span class="medium">Medium risk 40 to 69</span>
    <span class="high">High risk 70 and above</span>
  </div>
  <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
  <script>
    const points = {payload};
    const map = L.map("map").setView([23.5, 90.1], 7);
    L.tileLayer("https://tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png", {{
      maxZoom: 18,
      attribution: "&copy; OpenStreetMap contributors"
    }}).addTo(map);

    function riskColor(score) {{
      if (score >= 70) return "#ef4444";
      if (score >= 40) return "#f59e0b";
      return "#22c55e";
    }}

    points.forEach((point) => {{
      const circle = L.circleMarker([point.latitude, point.longitude], {{
        radius: 10,
        color: riskColor(point.risk_score),
        fillColor: riskColor(point.risk_score),
        fillOpacity: 0.82,
        weight: 2
      }});
      circle.bindPopup(
        `<strong>${{point.location_label}}</strong><br>` +
        `Region: ${{point.region_id}}<br>` +
        `Risk score: ${{point.risk_score}}<br>` +
        `Date: ${{point.target_date}}<br>` +
        `Drivers: ${{point.driver_summary}}`
      );
      circle.addTo(map);
    }});
  </script>
</body>
</html>
"""


def build_demo_outputs(
    *,
    results_dir: Path = RESULTS_DIR,
    data_dir: Path = DATA_DIR,
    site_path: Path = SITE_PATH,
) -> dict[str, object]:
    training = training_rows()
    ordered_weeks = sorted({str(row["target_date"]) for row in training})
    train_rows = [row for row in training if row["target_date"] != ordered_weeks[-1]]
    validation_rows = [row for row in training if row["target_date"] == ordered_weeks[-1]]

    model, model_family = build_regressor()
    model.fit(model_features(train_rows), [float(row["risk_score"]) for row in train_rows])

    validation_predictions = model.predict(model_features(validation_rows))
    validation_scores = [round(float(clamp(score, 0.0, 100.0)), 2) for score in validation_predictions]
    mae = mean_absolute_error([float(row["risk_score"]) for row in validation_rows], validation_scores)
    r2 = r2_score([float(row["risk_score"]) for row in validation_rows], validation_scores)

    scoring_source_mode, scoring_input_rows = scoring_rows()
    predicted_points = model.predict(model_features(scoring_input_rows))
    scored_points: list[dict[str, object]] = []
    for row, predicted_score in zip(scoring_input_rows, predicted_points, strict=True):
        scored_points.append(
            {
                **row,
                "risk_score": round(float(clamp(predicted_score, 0.0, 100.0)), 2),
            }
        )

    pilot = load_pilot_definition()
    report = {
        "pilot_name": pilot["pilot_name"],
        "model_family": model_family,
        "training_rows": len(training),
        "validation_rows": len(validation_rows),
        "validation_mae": round(float(mae), 3),
        "validation_r2": round(float(r2), 3),
        "training_source_mode": "proxy_fixture_labels",
        "scoring_source_mode": scoring_source_mode,
        "feature_names": [
            "rainfall_mm_7d",
            "flood_proxy",
            "sanitation_access_pct",
            "population_density_km2",
            "temperature_c",
            "surface_water_index",
        ],
    }

    results_dir.mkdir(parents=True, exist_ok=True)
    data_dir.mkdir(parents=True, exist_ok=True)
    site_path.parent.mkdir(parents=True, exist_ok=True)

    training_output = [
        {
            key: value
            for key, value in row.items()
            if key not in {"label_event", "case_count", "label_source"}
        }
        for row in training
    ]

    write_csv(results_dir / "synthetic_training_data.csv", training_output)
    write_csv(results_dir / "risk_scored_points.csv", scored_points)
    (results_dir / "model_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    (data_dir / "risk_scored_points.json").write_text(json.dumps(scored_points, indent=2), encoding="utf-8")

    map_html = render_map_html(
        "Waterborne Disease Risk Map",
        "Deterministic Bangladesh pilot demo built from locked repo fixtures and upgraded to live covariates when they exist.",
        scored_points,
    )
    (results_dir / "risk_map.html").write_text(map_html, encoding="utf-8")
    site_path.write_text(
        render_map_html(
            "OperationalDecisionSupportSystemForWaterSecurity Demo",
            "Static demo backed by the repo's pilot-aligned risk outputs in data/risk_scored_points.json.",
            scored_points,
        ),
        encoding="utf-8",
    )

    return {
        "results_dir": str(results_dir),
        "data_dir": str(data_dir),
        "site_path": str(site_path),
        "model_family": model_family,
        "validation_mae": round(float(mae), 3),
        "validation_r2": round(float(r2), 3),
        "scoring_source_mode": scoring_source_mode,
    }


def main() -> None:
    print(json.dumps(build_demo_outputs(), indent=2))


if __name__ == "__main__":
    main()
