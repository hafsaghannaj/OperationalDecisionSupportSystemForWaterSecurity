from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from geoalchemy2.elements import WKTElement
from sqlalchemy.orm import Session

from pipelines.ingest.common import IngestResult, create_source_run, file_checksum
from services.api.app.db_models import AdminBoundary


REQUIRED_COLUMNS = {"region_id", "name", "country_code", "admin_level", "geometry_wkt"}


@dataclass(slots=True)
class BoundaryRecord:
    region_id: str
    name: str
    country_code: str
    admin_level: int
    geometry_wkt: str | None


def parse_boundary_csv_row(row: Mapping[str, str]) -> BoundaryRecord:
    missing = REQUIRED_COLUMNS - set(row)
    if missing:
        raise ValueError(f"Boundary row is missing required columns: {sorted(missing)}")

    region_id = row["region_id"].strip()
    name = row["name"].strip()
    country_code = row["country_code"].strip()
    admin_level_raw = row["admin_level"].strip()
    geometry_wkt = row["geometry_wkt"].strip() or None

    if not region_id or not name or not country_code or not admin_level_raw:
        raise ValueError("Boundary row contains blank required values.")

    return BoundaryRecord(
        region_id=region_id,
        name=name,
        country_code=country_code,
        admin_level=int(admin_level_raw),
        geometry_wkt=geometry_wkt,
    )


def ingest_admin_boundaries_from_csv(
    session: Session,
    csv_path: str | Path,
    *,
    source_name: str = "admin_boundaries_csv",
) -> IngestResult:
    path = Path(csv_path).resolve()
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        rows = [parse_boundary_csv_row(row) for row in reader]

    source_run = create_source_run(
        session,
        source_name=source_name,
        upstream_asset_uri=str(path),
        record_count=len(rows),
        checksum=file_checksum(path),
    )

    inserted = 0
    updated = 0

    try:
        for row in rows:
            existing = session.get(AdminBoundary, row.region_id)
            geom = WKTElement(row.geometry_wkt, srid=4326) if row.geometry_wkt else None

            if existing is None:
                session.add(
                    AdminBoundary(
                        region_id=row.region_id,
                        name=row.name,
                        country_code=row.country_code,
                        admin_level=row.admin_level,
                        source_run_id=source_run.id,
                        geom=geom,
                    )
                )
                inserted += 1
            else:
                existing.name = row.name
                existing.country_code = row.country_code
                existing.admin_level = row.admin_level
                existing.source_run_id = source_run.id
                existing.geom = geom
                updated += 1

        session.commit()
    except Exception:
        session.rollback()
        raise

    return IngestResult(
        source_name=source_name,
        source_run_id=source_run.id,
        file_path=str(path),
        rows_read=len(rows),
        rows_inserted=inserted,
        rows_updated=updated,
    )
