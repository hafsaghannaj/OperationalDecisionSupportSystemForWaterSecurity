from __future__ import annotations

"""Fetch Bangladesh ADM2 boundaries from GeoBoundaries API and ingest to DB."""

import csv
import io
import logging
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import httpx
from geoalchemy2.elements import WKTElement
from sqlalchemy.orm import Session

from pipelines.ingest.common import IngestResult, create_source_run
from services.api.app.db_models import AdminBoundary

logger = logging.getLogger(__name__)

GEOBOUNDARIES_API_URL = (
    "https://www.geoboundaries.org/api/current/gbOpen/BGD/ADM2/"
)

# Hosts from which we are allowed to fetch boundary data.
_ALLOWED_DOWNLOAD_HOSTS: frozenset[str] = frozenset(
    {
        "www.geoboundaries.org",
        "geoboundaries.org",
        "github.com",
        "raw.githubusercontent.com",
    }
)


def _assert_safe_url(url: str, allowed_hosts: frozenset[str] = _ALLOWED_DOWNLOAD_HOSTS) -> None:
    """Raise ValueError if *url* is not a safe HTTPS URL for a known host."""
    parsed = urlparse(url)
    if parsed.scheme != "https":
        raise ValueError(f"Unsafe URL scheme: {parsed.scheme!r}. Only HTTPS is allowed.")
    if parsed.hostname not in allowed_hosts:
        raise ValueError(
            f"Untrusted download host: {parsed.hostname!r}. "
            f"Allowed hosts: {sorted(allowed_hosts)}"
        )


OCHA_POP_URL = (
    "https://data.humdata.org/dataset/fdf0606c-8a3b-421a-b3e8-903301e5b2ff"
    "/resource/43bfa9fd-f571-4973-9f31-91093e1e6142/download"
    "/bgd_admpop_adm2_2022.csv"
)


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------


def _ring_to_wkt(coords: list[list[float]]) -> str:
    """Convert a GeoJSON coordinate ring to a WKT coordinate string.

    Closes the ring by repeating the first point if necessary.
    """
    pts = list(coords)
    if pts and pts[0] != pts[-1]:
        pts.append(pts[0])
    return ", ".join(f"{x} {y}" for x, y in pts)


def _geom_to_wkt(geom: dict[str, Any]) -> str:
    """Convert a GeoJSON geometry dict to a WKT string.

    Handles Polygon and MultiPolygon geometry types.
    Coordinates are [longitude, latitude] pairs.
    """
    geom_type: str = geom.get("type", "")
    coordinates = geom.get("coordinates", [])

    if geom_type == "Polygon":
        rings = [f"({_ring_to_wkt(ring)})" for ring in coordinates]
        return f"POLYGON ({', '.join(rings)})"

    if geom_type == "MultiPolygon":
        polygons: list[str] = []
        for polygon_coords in coordinates:
            rings = [f"({_ring_to_wkt(ring)})" for ring in polygon_coords]
            polygons.append(f"({', '.join(rings)})")
        return f"MULTIPOLYGON ({', '.join(polygons)})"

    raise ValueError(
        f"Unsupported geometry type for WKT conversion: '{geom_type}'. "
        "Expected Polygon or MultiPolygon."
    )


# ---------------------------------------------------------------------------
# Data fetchers
# ---------------------------------------------------------------------------


def fetch_bgd_adm2_geojson() -> dict[str, Any]:
    """Call the GeoBoundaries API for Bangladesh ADM2 and return the GeoJSON dict.

    Makes two HTTP requests:
    1. GeoBoundaries metadata endpoint → extracts ``gjDownloadURL``
    2. The GeoJSON download URL → returns parsed GeoJSON

    Returns
    -------
    dict
        Parsed GeoJSON FeatureCollection with 64 district features.
    """
    logger.info("Fetching GeoBoundaries metadata from %s", GEOBOUNDARIES_API_URL)
    with httpx.Client(timeout=60.0, follow_redirects=True) as client:
        meta_resp = client.get(GEOBOUNDARIES_API_URL)
        meta_resp.raise_for_status()
        meta = meta_resp.json()

        geojson_url: str = meta["gjDownloadURL"]
        logger.info(
            "Fetched metadata; downloading GeoJSON from %s", geojson_url
        )
        _assert_safe_url(geojson_url)

        geojson_resp = client.get(geojson_url)
        geojson_resp.raise_for_status()
        geojson: dict[str, Any] = geojson_resp.json()

    feature_count = len(geojson.get("features", []))
    logger.info(
        "Downloaded GeoJSON with %d features from GeoBoundaries.", feature_count
    )
    return geojson


def _ocha_pcode_map() -> dict[str, str]:
    """Download OCHA population CSV and build a name → region_id mapping.

    Returns
    -------
    dict[str, str]
        Mapping of ``ADM2_NAME.upper()`` to ``region_id`` where
        ``region_id = "BD-" + ADM2_PCODE[2:]`` (e.g. "BARISAL" → "BD-1006").
    """
    logger.info("Fetching OCHA population CSV for pcode mapping.")
    with httpx.Client(timeout=60.0, follow_redirects=True) as client:
        resp = client.get(OCHA_POP_URL)
        resp.raise_for_status()
        content = resp.content.decode("utf-8-sig")

    reader = csv.DictReader(io.StringIO(content))
    pcode_map: dict[str, str] = {}
    for row in reader:
        adm2_pcode = row.get("ADM2_PCODE", "").strip()
        adm2_name = row.get("ADM2_NAME", "").strip()
        if not adm2_pcode.startswith("BD"):
            continue
        region_id = "BD-" + adm2_pcode[2:]
        pcode_map[adm2_name.upper()] = region_id

    logger.info("Built pcode map with %d entries.", len(pcode_map))
    return pcode_map


# ---------------------------------------------------------------------------
# Main ingest entry point
# ---------------------------------------------------------------------------


def ingest_bgd_boundaries(
    session: Session,
    *,
    source_name: str = "geoboundaries_bgd_adm2",
) -> IngestResult:
    """Fetch Bangladesh ADM2 boundaries from GeoBoundaries and upsert to DB.

    Parameters
    ----------
    session:
        Active SQLAlchemy session.
    source_name:
        Label recorded in the ``source_run`` audit table.

    Returns
    -------
    IngestResult
        Summary of rows read, inserted, and updated.
    """
    geojson = fetch_bgd_adm2_geojson()
    pcode_map = _ocha_pcode_map()

    features: list[dict[str, Any]] = geojson.get("features", [])
    geojson_url: str = geojson.get(
        "_download_url", GEOBOUNDARIES_API_URL
    )  # best-effort; overridden below

    # We don't have the download URL on the GeoJSON itself; reconstruct from
    # common usage.  The real URL is fetched inside fetch_bgd_adm2_geojson but
    # not returned.  Use the metadata endpoint as the upstream URI for the audit
    # record unless a better value is available.
    upstream_uri = GEOBOUNDARIES_API_URL

    source_run = create_source_run(
        session,
        source_name=source_name,
        upstream_asset_uri=upstream_uri,
        record_count=len(features),
        checksum=str(len(features)),  # lightweight stand-in; no local file
    )

    inserted = 0
    updated = 0

    try:
        for feature in features:
            props: dict[str, Any] = feature.get("properties") or {}
            shape_name: str = (props.get("shapeName") or "").strip()
            geometry: dict[str, Any] | None = feature.get("geometry")

            # Derive region_id from pcode map; fall back to mangled name.
            region_id: str = pcode_map.get(
                shape_name.upper(),
                "BD-" + shape_name[:8].upper().replace(" ", ""),
            )

            wkt: str | None = None
            if geometry:
                try:
                    wkt = _geom_to_wkt(geometry)
                except ValueError as exc:
                    logger.warning(
                        "Skipping geometry for %s: %s", shape_name, exc
                    )

            geom_elem = WKTElement(wkt, srid=4326) if wkt else None

            existing = session.get(AdminBoundary, region_id)
            if existing is None:
                session.add(
                    AdminBoundary(
                        region_id=region_id,
                        name=shape_name,
                        country_code="BD",
                        admin_level=2,
                        source_run_id=source_run.id,
                        geom=geom_elem,
                    )
                )
                inserted += 1
            else:
                existing.name = shape_name
                existing.country_code = "BD"
                existing.admin_level = 2
                existing.source_run_id = source_run.id
                existing.geom = geom_elem
                updated += 1

        session.commit()
    except Exception:
        session.rollback()
        raise

    logger.info(
        "ingest_bgd_boundaries: %d features fetched, %d inserted, %d updated.",
        len(features),
        inserted,
        updated,
    )

    return IngestResult(
        source_name=source_name,
        source_run_id=source_run.id,
        file_path=upstream_uri,
        rows_read=len(features),
        rows_inserted=inserted,
        rows_updated=updated,
    )
