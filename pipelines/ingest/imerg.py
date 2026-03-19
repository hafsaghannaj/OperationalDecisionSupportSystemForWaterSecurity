"""
IMERG-equivalent precipitation ingestion via Open-Meteo ERA5 archive.
No API key required. Writes weekly rainfall CSVs that the feature pipeline consumes.
"""
from __future__ import annotations

import csv
import urllib.request
import json
import logging
from datetime import date, timedelta
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.orm import Session

from services.api.app.db import SessionLocal

logger = logging.getLogger(__name__)

OPEN_METEO_URL = "https://archive-api.open-meteo.com/v1/archive"

# Fallback centroids for known Bangladesh districts (lon, lat)
FALLBACK_CENTROIDS: dict[str, tuple[float, float]] = {
    "BD-10": (89.5403, 22.8456),  # Khulna
    "BD-20": (90.3535, 22.7010),  # Barisal
    "BD-30": (90.4125, 23.8103),  # Dhaka
}

OUTPUT_DIR = Path(__file__).parents[3] / "data" / "imerg"


def _get_region_centroids(session: Session) -> dict[str, tuple[float, float]]:
    """Return {region_id: (lon, lat)} using PostGIS ST_Centroid where available."""
    try:
        rows = session.execute(
            text(
                "SELECT region_id, "
                "ST_X(ST_Centroid(geom)) AS lon, "
                "ST_Y(ST_Centroid(geom)) AS lat "
                "FROM admin_boundaries WHERE geom IS NOT NULL"
            )
        ).all()
        centroids = {row.region_id: (float(row.lon), float(row.lat)) for row in rows}
    except Exception as exc:
        logger.warning("Could not derive centroids from PostGIS, using fallbacks: %s", exc)
        centroids = {}

    # Fill in fallbacks for any missing regions
    for region_id, coords in FALLBACK_CENTROIDS.items():
        if region_id not in centroids:
            centroids[region_id] = coords

    return centroids


def _iso(d: date) -> str:
    return d.isoformat()


def _fetch_daily_precipitation(lat: float, lon: float, start: date, end: date) -> dict[str, float]:
    """Return {date_str: mm} from Open-Meteo archive API."""
    params = (
        f"?latitude={lat:.4f}&longitude={lon:.4f}"
        f"&start_date={_iso(start)}&end_date={_iso(end)}"
        f"&daily=precipitation_sum&timezone=UTC"
    )
    url = OPEN_METEO_URL + params
    try:
        with urllib.request.urlopen(url, timeout=30) as resp:
            data = json.loads(resp.read().decode())
        dates = data["daily"]["time"]
        values = data["daily"]["precipitation_sum"]
        return {d: float(v) if v is not None else 0.0 for d, v in zip(dates, values)}
    except Exception as exc:
        logger.error("Open-Meteo fetch failed for lat=%.4f lon=%.4f: %s", lat, lon, exc)
        return {}


def _week_starts(n_weeks: int = 12, reference: date | None = None) -> list[date]:
    """Return ISO week start dates (Monday) for the last n_weeks."""
    ref = reference or date.today()
    # Walk back to last Monday
    current = ref - timedelta(days=ref.weekday())
    weeks = []
    for _ in range(n_weeks):
        weeks.append(current)
        current -= timedelta(weeks=1)
    return sorted(weeks)


def _weekly_sum(daily: dict[str, float], week_start: date) -> float:
    """Sum daily precipitation over 7 days starting at week_start."""
    total = 0.0
    for i in range(7):
        day = week_start + timedelta(days=i)
        total += daily.get(_iso(day), 0.0)
    return round(total, 2)


def ingest_imerg(
    *,
    session: Session | None = None,
    n_weeks: int = 12,
    reference_date: date | None = None,
    output_path: Path | None = None,
) -> str:
    """
    Fetch weekly precipitation for all districts from Open-Meteo and write to CSV.
    Returns the path of the written file as a summary string.
    """
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out = output_path or OUTPUT_DIR / f"imerg_weather_{date.today().isoformat()}.csv"
    latest_link = OUTPUT_DIR / "latest.csv"

    week_starts = _week_starts(n_weeks=n_weeks, reference=reference_date)
    # Fetch range: from first week_start to last week_start + 6 days
    fetch_start = week_starts[0]
    fetch_end = week_starts[-1] + timedelta(days=6)

    ctx = session if session is not None else SessionLocal()
    own_session = session is None

    try:
        centroids = _get_region_centroids(ctx)
    finally:
        if own_session:
            ctx.close()

    rows: list[dict[str, str]] = []
    for region_id, (lon, lat) in centroids.items():
        logger.info("Fetching precipitation for %s (%.4f, %.4f)", region_id, lat, lon)
        daily = _fetch_daily_precipitation(lat=lat, lon=lon, start=fetch_start, end=fetch_end)
        for week_start in week_starts:
            weekly_mm = _weekly_sum(daily, week_start)
            rows.append({
                "region_id": region_id,
                "week_start_date": _iso(week_start),
                "rainfall_total_mm_7d": str(weekly_mm),
            })

    with out.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=["region_id", "week_start_date", "rainfall_total_mm_7d"])
        writer.writeheader()
        writer.writerows(rows)

    # Keep a stable "latest" symlink / copy for the feature pipeline
    if latest_link.exists() or latest_link.is_symlink():
        latest_link.unlink()
    latest_link.symlink_to(out.name)

    logger.info("IMERG ingest complete: %d rows written to %s", len(rows), out)
    return str(out)
