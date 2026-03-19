#!/usr/bin/env python3
"""
Seed synthetic risk data for all pilot countries.

Inserts admin_boundaries, risk_scores, and alert_events for every country
in the pilot registry (skips rows that already exist via ON CONFLICT DO NOTHING).

Usage (inside api/worker container):
    python scripts/seed_multi_country.py

Or via docker exec:
    docker exec <api-container> python /app/scripts/seed_multi_country.py
"""
from __future__ import annotations

import json
import os
import uuid
from datetime import date

import psycopg

DATABASE_URL = os.environ.get(
    "ODSSWS_DATABASE_URL",
    os.environ.get("AQUAINTEL_DATABASE_URL", "postgresql://odssws:odssws@db:5432/odssws"),
)

# Latest ISO week Monday
LATEST_WEEK = date(2026, 3, 16)
MODEL_VERSION = "demo-v1.0"

DISTRICTS = [
    # ── Kenya ──────────────────────────────────────────────────────────
    {
        "region_id": "KE-001", "name": "Nairobi County", "country_code": "KE",
        "lon": 36.82, "lat": -1.29, "score": 0.32, "confidence": "low",
        "drivers": {"wash_access_gap": 0.12, "rainfall_anomaly": 0.08, "population_density": 0.12},
        "narrative": "Nairobi shows low risk this week. Rainfall within seasonal norms and WASH coverage is high.",
        "severity": None,
    },
    {
        "region_id": "KE-002", "name": "Mombasa County", "country_code": "KE",
        "lon": 39.67, "lat": -4.05, "score": 0.61, "confidence": "medium",
        "drivers": {"rainfall_anomaly": 0.25, "lag_case_count_1w": 0.22, "sanitation_gap": 0.14},
        "narrative": "Elevated rainfall anomaly and lagged case signal drive moderate risk in Mombasa.",
        "severity": "medium",
    },
    {
        "region_id": "KE-003", "name": "Kisumu County", "country_code": "KE",
        "lon": 34.76, "lat": -0.09, "score": 0.78, "confidence": "high",
        "drivers": {"surface_water_index": 0.35, "sanitation_gap": 0.28, "lag_case_count_1w": 0.15},
        "narrative": "High surface water index near Lake Victoria and poor sanitation coverage drive HIGH risk.",
        "severity": "high",
    },
    # ── Nigeria ────────────────────────────────────────────────────────
    {
        "region_id": "NG-001", "name": "Lagos State", "country_code": "NG",
        "lon": 3.39, "lat": 6.52, "score": 0.55, "confidence": "medium",
        "drivers": {"population_density": 0.22, "rainfall_anomaly": 0.18, "sanitation_gap": 0.15},
        "narrative": "Dense population and above-average rainfall create medium risk conditions in Lagos.",
        "severity": "medium",
    },
    {
        "region_id": "NG-002", "name": "Kano State", "country_code": "NG",
        "lon": 8.53, "lat": 12.00, "score": 0.41, "confidence": "medium",
        "drivers": {"wash_access_gap": 0.20, "lag_case_count_1w": 0.12, "rainfall_anomaly": 0.09},
        "narrative": "Moderate WASH access gap and previous-week case signal maintain medium alert level.",
        "severity": "medium",
    },
    {
        "region_id": "NG-003", "name": "Rivers State", "country_code": "NG",
        "lon": 7.03, "lat": 4.83, "score": 0.72, "confidence": "high",
        "drivers": {"flood_proxy": 0.30, "sanitation_gap": 0.25, "rainfall_anomaly": 0.17},
        "narrative": "Flood proxy score and persistent sanitation deficit elevate risk in Rivers State.",
        "severity": "high",
    },
    # ── Ethiopia ───────────────────────────────────────────────────────
    {
        "region_id": "ET-001", "name": "Addis Ababa", "country_code": "ET",
        "lon": 38.74, "lat": 8.99, "score": 0.28, "confidence": "low",
        "drivers": {"wash_access_gap": 0.10, "rainfall_anomaly": 0.09, "population_density": 0.09},
        "narrative": "Addis Ababa maintains low risk with improving WASH coverage and dry conditions.",
        "severity": None,
    },
    {
        "region_id": "ET-002", "name": "Oromia Region", "country_code": "ET",
        "lon": 39.55, "lat": 7.65, "score": 0.67, "confidence": "medium",
        "drivers": {"rainfall_anomaly": 0.28, "lag_case_count_1w": 0.22, "sanitation_gap": 0.17},
        "narrative": "Seasonal rainfall spike and prior-week case counts elevate risk across Oromia.",
        "severity": "medium",
    },
    {
        "region_id": "ET-003", "name": "Amhara Region", "country_code": "ET",
        "lon": 37.85, "lat": 11.35, "score": 0.81, "confidence": "high",
        "drivers": {"lag_case_count_1w": 0.38, "rainfall_anomaly": 0.26, "wash_access_gap": 0.17},
        "narrative": "Persistent case signal from prior weeks and rainfall anomaly drive HIGH risk in Amhara.",
        "severity": "high",
    },
    # ── Pakistan ───────────────────────────────────────────────────────
    {
        "region_id": "PK-001", "name": "Karachi District", "country_code": "PK",
        "lon": 67.01, "lat": 24.87, "score": 0.58, "confidence": "medium",
        "drivers": {"population_density": 0.25, "sanitation_gap": 0.20, "rainfall_anomaly": 0.13},
        "narrative": "Urban density and sanitation infrastructure gaps drive medium risk in Karachi.",
        "severity": "medium",
    },
    {
        "region_id": "PK-002", "name": "Lahore District", "country_code": "PK",
        "lon": 74.35, "lat": 31.52, "score": 0.35, "confidence": "low",
        "drivers": {"rainfall_anomaly": 0.12, "wash_access_gap": 0.10, "lag_case_count_1w": 0.08},
        "narrative": "Lahore shows low risk this week with stable case counts and normal rainfall.",
        "severity": None,
    },
    {
        "region_id": "PK-003", "name": "Peshawar District", "country_code": "PK",
        "lon": 71.56, "lat": 34.01, "score": 0.76, "confidence": "high",
        "drivers": {"lag_case_count_1w": 0.32, "flood_proxy": 0.28, "sanitation_gap": 0.16},
        "narrative": "Elevated case carry-over and flood proxy signal demand attention in Peshawar.",
        "severity": "high",
    },
    # ── India ──────────────────────────────────────────────────────────
    {
        "region_id": "IN-001", "name": "Mumbai District", "country_code": "IN",
        "lon": 72.87, "lat": 19.07, "score": 0.44, "confidence": "medium",
        "drivers": {"rainfall_anomaly": 0.20, "population_density": 0.15, "sanitation_gap": 0.09},
        "narrative": "Monsoon tail and dense informal settlements maintain medium risk in Mumbai.",
        "severity": "medium",
    },
    {
        "region_id": "IN-002", "name": "Kolkata District", "country_code": "IN",
        "lon": 88.36, "lat": 22.57, "score": 0.69, "confidence": "medium",
        "drivers": {"flood_proxy": 0.30, "lag_case_count_1w": 0.22, "sanitation_gap": 0.17},
        "narrative": "Flood-prone delta location and lagged case signal keep Kolkata at medium-high risk.",
        "severity": "medium",
    },
    {
        "region_id": "IN-003", "name": "Chennai District", "country_code": "IN",
        "lon": 80.27, "lat": 13.08, "score": 0.38, "confidence": "low",
        "drivers": {"wash_access_gap": 0.15, "rainfall_anomaly": 0.12, "lag_case_count_1w": 0.08},
        "narrative": "Chennai shows low risk with adequate WASH access and below-seasonal rainfall.",
        "severity": None,
    },
    # ── Mozambique ─────────────────────────────────────────────────────
    {
        "region_id": "MZ-001", "name": "Maputo City", "country_code": "MZ",
        "lon": 32.59, "lat": -25.97, "score": 0.52, "confidence": "medium",
        "drivers": {"rainfall_anomaly": 0.22, "sanitation_gap": 0.18, "lag_case_count_1w": 0.12},
        "narrative": "Post-cyclone rainfall recovery keeps medium alert status in Maputo.",
        "severity": "medium",
    },
    {
        "region_id": "MZ-002", "name": "Beira District", "country_code": "MZ",
        "lon": 34.83, "lat": -19.84, "score": 0.83, "confidence": "high",
        "drivers": {"flood_proxy": 0.40, "rainfall_anomaly": 0.28, "lag_case_count_1w": 0.15},
        "narrative": "Coastal flooding and cyclone history make Beira the highest-risk district in Mozambique.",
        "severity": "high",
    },
    {
        "region_id": "MZ-003", "name": "Nampula District", "country_code": "MZ",
        "lon": 39.26, "lat": -15.12, "score": 0.45, "confidence": "medium",
        "drivers": {"wash_access_gap": 0.20, "lag_case_count_1w": 0.15, "rainfall_anomaly": 0.10},
        "narrative": "Moderate WASH access gap and seasonal rains maintain medium risk in Nampula.",
        "severity": "medium",
    },
    # ── Haiti ──────────────────────────────────────────────────────────
    {
        "region_id": "HT-001", "name": "Port-au-Prince", "country_code": "HT",
        "lon": -72.34, "lat": 18.54, "score": 0.87, "confidence": "high",
        "drivers": {"sanitation_gap": 0.45, "lag_case_count_1w": 0.32, "surface_water_index": 0.10},
        "narrative": "Chronic sanitation deficit and active case transmission drive critical risk in Port-au-Prince.",
        "severity": "high",
    },
    {
        "region_id": "HT-002", "name": "Cap-Haitien", "country_code": "HT",
        "lon": -72.20, "lat": 19.76, "score": 0.64, "confidence": "medium",
        "drivers": {"lag_case_count_1w": 0.28, "wash_access_gap": 0.22, "rainfall_anomaly": 0.14},
        "narrative": "Lagged case transmission from the capital and poor water access elevate risk.",
        "severity": "medium",
    },
    {
        "region_id": "HT-003", "name": "Gonaïves", "country_code": "HT",
        "lon": -72.69, "lat": 19.44, "score": 0.79, "confidence": "high",
        "drivers": {"flood_proxy": 0.35, "sanitation_gap": 0.30, "lag_case_count_1w": 0.14},
        "narrative": "Flood-prone Artibonite valley and high sanitation deficit drive HIGH alert in Gonaïves.",
        "severity": "high",
    },
    # ── Sudan ──────────────────────────────────────────────────────────
    {
        "region_id": "SD-001", "name": "Khartoum State", "country_code": "SD",
        "lon": 32.53, "lat": 15.55, "score": 0.42, "confidence": "medium",
        "drivers": {"rainfall_anomaly": 0.18, "wash_access_gap": 0.15, "population_density": 0.09},
        "narrative": "Nile flooding risk and moderate WASH gap maintain medium alert in Khartoum.",
        "severity": "medium",
    },
    {
        "region_id": "SD-002", "name": "Omdurman", "country_code": "SD",
        "lon": 32.48, "lat": 15.65, "score": 0.56, "confidence": "medium",
        "drivers": {"population_density": 0.22, "sanitation_gap": 0.20, "lag_case_count_1w": 0.14},
        "narrative": "High population density and sanitation infrastructure strain elevate risk in Omdurman.",
        "severity": "medium",
    },
    {
        "region_id": "SD-003", "name": "Port Sudan", "country_code": "SD",
        "lon": 37.22, "lat": 19.62, "score": 0.73, "confidence": "high",
        "drivers": {"lag_case_count_1w": 0.30, "flood_proxy": 0.25, "wash_access_gap": 0.18},
        "narrative": "Active case transmission and coastal flood exposure drive HIGH risk in Port Sudan.",
        "severity": "high",
    },
    # ── Yemen ──────────────────────────────────────────────────────────
    {
        "region_id": "YE-001", "name": "Sanaa City", "country_code": "YE",
        "lon": 44.21, "lat": 15.35, "score": 0.88, "confidence": "high",
        "drivers": {"lag_case_count_1w": 0.42, "sanitation_gap": 0.28, "wash_access_gap": 0.18},
        "narrative": "Ongoing conflict-driven collapse of water and sanitation systems drives critical risk.",
        "severity": "high",
    },
    {
        "region_id": "YE-002", "name": "Aden Governorate", "country_code": "YE",
        "lon": 45.03, "lat": 12.78, "score": 0.74, "confidence": "high",
        "drivers": {"lag_case_count_1w": 0.32, "flood_proxy": 0.22, "sanitation_gap": 0.20},
        "narrative": "Port city with damaged infrastructure and persistent case signal — HIGH alert maintained.",
        "severity": "high",
    },
    {
        "region_id": "YE-003", "name": "Hodeidah Governorate", "country_code": "YE",
        "lon": 42.95, "lat": 14.80, "score": 0.91, "confidence": "high",
        "drivers": {"lag_case_count_1w": 0.45, "sanitation_gap": 0.32, "flood_proxy": 0.14},
        "narrative": "Highest risk district: active outbreak signal, destroyed sanitation, Red Sea flooding history.",
        "severity": "high",
    },
]

ALERT_ACTIONS = {
    "high": "Deploy field surveillance teams immediately. Initiate emergency WASH response. Alert district health officer.",
    "medium": "Increase community health worker monitoring. Pre-position ORS stocks. Weekly situational report to WASH lead.",
}


def run() -> None:
    # psycopg3 — strip async driver prefix if present
    url = DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://").replace("postgresql+psycopg://", "postgresql://")
    conn = psycopg.connect(url)
    cur = conn.cursor()

    inserted_boundaries = 0
    inserted_scores = 0
    inserted_alerts = 0
    skipped = 0

    for d in DISTRICTS:
        lon, lat = d["lon"], d["lat"]

        # 1. Admin boundary (approximate circle, ~0.4° radius ≈ 44 km)
        cur.execute(
            """
            INSERT INTO admin_boundaries
                (region_id, name, country_code, admin_level, geom)
            VALUES (
                %s, %s, %s, 2,
                ST_Multi(ST_Buffer(ST_SetSRID(ST_MakePoint(%s, %s), 4326), 0.4))
            )
            ON CONFLICT (region_id) DO NOTHING
            """,
            (d["region_id"], d["name"], d["country_code"], lon, lat),
        )
        inserted_boundaries += cur.rowcount

        # 2. Risk score
        cur.execute(
            """
            INSERT INTO risk_scores
                (id, region_id, week_start_date, model_version, score, confidence,
                 driver_contributions, driver_narrative)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (region_id, week_start_date) DO NOTHING
            """,
            (
                str(uuid.uuid4()),
                d["region_id"],
                LATEST_WEEK,
                MODEL_VERSION,
                d["score"],
                d["confidence"],
                json.dumps(d["drivers"]),
                d["narrative"],
            ),
        )
        inserted_scores += cur.rowcount
        if cur.rowcount == 0:
            skipped += 1

        # 3. Alert event (medium or high only)
        if d["severity"] in ("medium", "high"):
            cur.execute(
                """
                INSERT INTO alert_events
                    (id, region_id, week_start_date, severity, recommended_action, status)
                VALUES (%s, %s, %s, %s, %s, 'open')
                ON CONFLICT (region_id, week_start_date) DO NOTHING
                """,
                (
                    str(uuid.uuid4()),
                    d["region_id"],
                    LATEST_WEEK,
                    d["severity"],
                    ALERT_ACTIONS[d["severity"]],
                ),
            )
            inserted_alerts += cur.rowcount

    conn.commit()
    cur.close()
    conn.close()

    print(f"Done. boundaries={inserted_boundaries} scores={inserted_scores} "
          f"alerts={inserted_alerts} skipped(scores)={skipped}")


if __name__ == "__main__":
    run()
