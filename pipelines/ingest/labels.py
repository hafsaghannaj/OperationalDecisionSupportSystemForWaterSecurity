from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Mapping

from sqlalchemy import select
from sqlalchemy.orm import Session

from pipelines.ingest.common import IngestResult, create_source_run, file_checksum, parse_bool
from services.api.app.db_models import AdminBoundary, DistrictWeekLabel


REQUIRED_COLUMNS = {
    "region_id",
    "week_start_date",
    "label_event",
    "case_count",
    "label_source",
    "label_observed_at",
}


@dataclass(slots=True)
class LabelRecord:
    region_id: str
    week_start_date: date
    label_event: bool
    case_count: int | None
    label_source: str
    label_observed_at: date | None


def parse_label_csv_row(row: Mapping[str, str]) -> LabelRecord:
    missing = REQUIRED_COLUMNS - set(row)
    if missing:
        raise ValueError(f"Label row is missing required columns: {sorted(missing)}")

    region_id = row["region_id"].strip()
    week_start_raw = row["week_start_date"].strip()
    label_event_raw = row["label_event"].strip()
    case_count_raw = row["case_count"].strip()
    label_source = row["label_source"].strip()
    label_observed_raw = row["label_observed_at"].strip()

    if not region_id or not week_start_raw or not label_event_raw or not label_source:
        raise ValueError("Label row contains blank required values.")

    return LabelRecord(
        region_id=region_id,
        week_start_date=date.fromisoformat(week_start_raw),
        label_event=parse_bool(label_event_raw),
        case_count=int(case_count_raw) if case_count_raw else None,
        label_source=label_source,
        label_observed_at=date.fromisoformat(label_observed_raw) if label_observed_raw else None,
    )


def ingest_historical_labels_from_csv(
    session: Session,
    csv_path: str | Path,
    *,
    source_name: str = "historical_labels_csv",
) -> IngestResult:
    path = Path(csv_path).resolve()
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        rows = [parse_label_csv_row(row) for row in reader]

    known_regions = {
        region_id
        for region_id in session.scalars(select(AdminBoundary.region_id)).all()
    }
    missing_regions = sorted({row.region_id for row in rows} - known_regions)
    if missing_regions:
        raise ValueError(
            "Historical label ingest references unknown regions: "
            + ", ".join(missing_regions)
            + ". Load admin boundaries first."
        )

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
            existing = session.scalar(
                select(DistrictWeekLabel).where(
                    DistrictWeekLabel.region_id == row.region_id,
                    DistrictWeekLabel.week_start_date == row.week_start_date,
                    DistrictWeekLabel.label_source == row.label_source,
                )
            )

            if existing is None:
                session.add(
                    DistrictWeekLabel(
                        region_id=row.region_id,
                        week_start_date=row.week_start_date,
                        label_event=row.label_event,
                        case_count=row.case_count,
                        label_source=row.label_source,
                        label_observed_at=row.label_observed_at,
                        source_run_id=source_run.id,
                    )
                )
                inserted += 1
            else:
                existing.label_event = row.label_event
                existing.case_count = row.case_count
                existing.label_observed_at = row.label_observed_at
                existing.source_run_id = source_run.id
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
