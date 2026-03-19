from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, timedelta
from pathlib import Path
import csv
import json
import math
import random

from sklearn.ensemble import GradientBoostingRegressor
from sklearn.metrics import mean_absolute_error, r2_score


REPO_ROOT = Path(__file__).resolve().parents[2]
RESULTS_DIR = REPO_ROOT / "results"
DATA_DIR = REPO_ROOT / "data"
SITE_PATH = REPO_ROOT / "index.html"
MAP_PATH = RESULTS_DIR / "risk_map.html"


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


@dataclass(frozen=True)
class TrainingRow:
    latitude: float
    longitude: float
    target_date: str
    rainfall_mm_7d: float
    flood_proxy: float
    sanitation_access_pct: float
    population_density_km2: float
    temperature_c: float
    surface_water_index: float
    risk_score: float


@dataclass(frozen=True)
class ScoredPoint:
    location_label: str
    latitude: float
    longitude: float
    target_date: str
    rainfall_mm_7d: float
    flood_proxy: float
    sanitation_access_pct: float
    population_density_km2: float
    temperature_c: float
    surface_water_index: float
    risk_score: float


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


def training_rows(seed: int = 42) -> list[TrainingRow]:
    rng = random.Random(seed)
    rows: list[TrainingRow] = []
    start_date = date(2025, 1, 6)

    for week_index in range(16):
        target_date = start_date + timedelta(days=7 * week_index)
        seasonal_pressure = 0.5 + 0.5 * math.sin(week_index / 2.5)
        for district_index in range(8):
            latitude = 21.9 + district_index * 0.36 + rng.uniform(-0.05, 0.05)
            longitude = 89.2 + district_index * 0.22 + rng.uniform(-0.08, 0.08)
            rainfall = clamp(75 + seasonal_pressure * 115 + rng.uniform(-18, 28), 20, 260)
            flood_proxy = clamp(0.18 + seasonal_pressure * 0.62 + rng.uniform(-0.08, 0.12), 0.0, 1.0)
            sanitation = clamp(78 - district_index * 4.5 + rng.uniform(-6, 5), 28, 96)
            density = clamp(620 + district_index * 430 + rng.uniform(-180, 280), 150, 5200)
            temperature = clamp(24 + seasonal_pressure * 8 + rng.uniform(-1.5, 1.5), 21, 34)
            surface_water = clamp(0.15 + seasonal_pressure * 0.55 + rng.uniform(-0.1, 0.1), 0.0, 1.0)

            density_factor = clamp((density - 150) / 5050, 0.0, 1.0)
            sanitation_factor = 1.0 - sanitation / 100.0
            rainfall_factor = rainfall / 260.0
            temperature_factor = clamp((temperature - 21) / 13, 0.0, 1.0)
            risk_score = clamp(
                100
                * (
                    0.29 * rainfall_factor
                    + 0.24 * flood_proxy
                    + 0.17 * sanitation_factor
                    + 0.14 * density_factor
                    + 0.10 * surface_water
                    + 0.06 * temperature_factor
                    + rng.uniform(-0.05, 0.05)
                ),
                4,
                98,
            )

            rows.append(
                TrainingRow(
                    latitude=round(latitude, 5),
                    longitude=round(longitude, 5),
                    target_date=target_date.isoformat(),
                    rainfall_mm_7d=round(rainfall, 2),
                    flood_proxy=round(flood_proxy, 3),
                    sanitation_access_pct=round(sanitation, 2),
                    population_density_km2=round(density, 2),
                    temperature_c=round(temperature, 2),
                    surface_water_index=round(surface_water, 3),
                    risk_score=round(risk_score, 2),
                )
            )

    return rows


def scoring_points() -> list[ScoredPoint]:
    base_date = "2026-03-22"
    return [
        ScoredPoint("Khulna River Delta", 22.81, 89.55, base_date, 228.0, 0.91, 41.0, 2340.0, 31.0, 0.88, 0.0),
        ScoredPoint("Barisal Floodplain", 22.72, 90.36, base_date, 198.0, 0.79, 48.0, 1980.0, 30.3, 0.74, 0.0),
        ScoredPoint("Dhaka Periphery", 23.88, 90.41, base_date, 166.0, 0.55, 62.0, 4610.0, 31.6, 0.49, 0.0),
        ScoredPoint("Sylhet Tea Belt", 24.87, 91.92, base_date, 144.0, 0.46, 67.0, 1260.0, 29.9, 0.58, 0.0),
        ScoredPoint("Rajshahi Northwest", 24.37, 88.61, base_date, 82.0, 0.19, 74.0, 930.0, 30.1, 0.18, 0.0),
    ]


def feature_matrix(rows: list[TrainingRow]) -> list[list[float]]:
    return [
        [
            row.rainfall_mm_7d,
            row.flood_proxy,
            row.sanitation_access_pct,
            row.population_density_km2,
            row.temperature_c,
            row.surface_water_index,
        ]
        for row in rows
    ]


def score_matrix(rows: list[ScoredPoint]) -> list[list[float]]:
    return [
        [
            row.rainfall_mm_7d,
            row.flood_proxy,
            row.sanitation_access_pct,
            row.population_density_km2,
            row.temperature_c,
            row.surface_water_index,
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
    .hero {{
      padding: 24px 24px 12px;
    }}
    h1 {{
      margin: 0 0 6px;
      font-size: 1.8rem;
    }}
    p {{
      margin: 0;
      color: #9fc0d4;
      max-width: 60rem;
    }}
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
        `Risk score: ${{point.risk_score}}<br>` +
        `Date: ${{point.target_date}}<br>` +
        `Rainfall: ${{point.rainfall_mm_7d}} mm`
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
    train_rows = training_rows()
    split_index = int(len(train_rows) * 0.8)
    train_slice = train_rows[:split_index]
    validation_slice = train_rows[split_index:]
    model, model_family = build_regressor()
    model.fit(feature_matrix(train_slice), [row.risk_score for row in train_slice])

    validation_predictions = model.predict(feature_matrix(validation_slice))
    validation_scores = [round(float(value), 2) for value in validation_predictions]
    mae = mean_absolute_error([row.risk_score for row in validation_slice], validation_scores)
    r2 = r2_score([row.risk_score for row in validation_slice], validation_scores)

    predicted_points = model.predict(score_matrix(scoring_points()))
    scored_points: list[dict[str, object]] = []
    for point, predicted_score in zip(scoring_points(), predicted_points, strict=True):
        scored_points.append(
            {
                **asdict(point),
                "risk_score": round(float(clamp(predicted_score, 0.0, 100.0)), 2),
            }
        )

    training_output = [asdict(row) for row in train_rows]
    report = {
        "model_family": model_family,
        "training_rows": len(train_rows),
        "validation_rows": len(validation_slice),
        "validation_mae": round(float(mae), 3),
        "validation_r2": round(float(r2), 3),
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
    write_csv(results_dir / "synthetic_training_data.csv", training_output)
    write_csv(results_dir / "risk_scored_points.csv", scored_points)
    (results_dir / "model_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    (data_dir / "risk_scored_points.json").write_text(json.dumps(scored_points, indent=2), encoding="utf-8")

    map_html = render_map_html(
        "Waterborne Disease Risk Map",
        "Synthetic multi-modal demo outputs for the current OperationalDecisionSupportSystemForWaterSecurity repo.",
        scored_points,
    )
    (results_dir / "risk_map.html").write_text(map_html, encoding="utf-8")
    site_path.write_text(
        render_map_html(
            "OperationalDecisionSupportSystemForWaterSecurity Demo",
            "Static GitHub Pages style demo built from precomputed risk scores in data/risk_scored_points.json.",
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
    }


def main() -> None:
    summary = build_demo_outputs()
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
