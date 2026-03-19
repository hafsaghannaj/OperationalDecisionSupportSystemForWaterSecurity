from __future__ import annotations

import csv
import io
from dataclasses import asdict, dataclass
from datetime import date
import os
from pathlib import Path
import re
from typing import Mapping

import httpx
from sqlalchemy import distinct, select
from sqlalchemy.orm import Session

from pipelines.ingest.common import IngestResult, create_source_run, data_dir, file_checksum, parse_bool
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


@dataclass(slots=True)
class RealLabelFeedConfig:
    mode: str
    label_source: str
    case_threshold: int
    export_url: str | None = None
    export_path: str | None = None
    username: str | None = None
    password: str | None = None


@dataclass(slots=True)
class LabelValidationIssue:
    row_number: int
    message: str
    row_excerpt: dict[str, str]

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(slots=True)
class LabelValidationResult:
    label_source: str
    upstream_asset_uri: str
    rows_read: int
    valid_rows: int
    invalid_rows: int
    aggregated_rows: int
    distinct_regions: int
    earliest_week: str | None
    latest_week: str | None
    normalized_path: str | None
    issues: list[LabelValidationIssue]

    def as_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["issues"] = [issue.as_dict() for issue in self.issues]
        return payload


_WEEK_RE = re.compile(r"^(?P<year>\d{4})-?W(?P<week>\d{1,2})(?:[A-Za-z]+)?$")
_ORG_UNIT_ALIASES = {
    "barishal": "barisal",
    "chattogram": "chittagong",
    "jashore": "jessore",
    "cumilla": "comilla",
    "bagerhat sadar": "bagerhat",
    "khulna sadar": "khulna",
    "barisal sadar": "barisal",
    "dhaka sadar": "dhaka",
}


def _env(*names: str) -> str | None:
    for name in names:
        value = os.getenv(name)
        if value:
            return value
    return None


def load_real_label_feed_config() -> RealLabelFeedConfig | None:
    mode = _env("ODSSWS_REAL_LABELS_MODE", "AQUAINTEL_REAL_LABELS_MODE")
    if not mode or mode == "disabled":
        return None

    return RealLabelFeedConfig(
        mode=mode,
        label_source=_env("ODSSWS_REAL_LABELS_SOURCE", "AQUAINTEL_REAL_LABELS_SOURCE") or "dghs_dhis2_weekly_cases",
        case_threshold=int(_env("ODSSWS_REAL_LABEL_CASE_THRESHOLD", "AQUAINTEL_REAL_LABEL_CASE_THRESHOLD") or "1"),
        export_url=_env("ODSSWS_DHIS2_LABEL_EXPORT_URL", "AQUAINTEL_DHIS2_LABEL_EXPORT_URL"),
        export_path=_env("ODSSWS_DHIS2_LABEL_EXPORT_PATH", "AQUAINTEL_DHIS2_LABEL_EXPORT_PATH"),
        username=_env("ODSSWS_DHIS2_USERNAME", "AQUAINTEL_DHIS2_USERNAME"),
        password=_env("ODSSWS_DHIS2_PASSWORD", "AQUAINTEL_DHIS2_PASSWORD"),
    )


def normalize_org_unit_name(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", " ", value.strip().lower()).strip()
    return _ORG_UNIT_ALIASES.get(normalized, normalized)


def build_region_lookup(session: Session) -> dict[str, str]:
    rows = session.execute(select(AdminBoundary.region_id, AdminBoundary.name)).all()
    lookup: dict[str, str] = {}
    for row in rows:
        lookup[normalize_org_unit_name(row.name)] = row.region_id
    return lookup


def load_label_weeks(session: Session, *, label_source: str | None = None) -> list[date]:
    stmt = select(distinct(DistrictWeekLabel.week_start_date)).order_by(DistrictWeekLabel.week_start_date)
    if label_source is not None:
        stmt = stmt.where(DistrictWeekLabel.label_source == label_source)
    return list(session.scalars(stmt).all())


def parse_period_to_week_start(value: str) -> date:
    raw = value.strip()
    if not raw:
        raise ValueError("Period value is blank.")

    try:
        return date.fromisoformat(raw)
    except ValueError:
        pass

    match = _WEEK_RE.match(raw)
    if match:
        return date.fromisocalendar(int(match.group("year")), int(match.group("week")), 1)

    raise ValueError(f"Unsupported DHIS2 period format '{value}'.")


def _first_value(row: Mapping[str, str], *candidates: str) -> str | None:
    lowered = {key.lower(): value for key, value in row.items()}
    for candidate in candidates:
        if candidate.lower() in lowered:
            return lowered[candidate.lower()]
    return None


def resolve_region_id_from_export_row(
    row: Mapping[str, str],
    *,
    region_lookup: Mapping[str, str],
) -> str:
    explicit_region_id = _first_value(row, "region_id")
    if explicit_region_id:
        return explicit_region_id.strip().upper()

    org_unit_code = _first_value(row, "organisation unit code", "organization unit code", "org unit code", "oucode")
    if org_unit_code:
        normalized_code = org_unit_code.strip().upper().replace(" ", "")
        if normalized_code.startswith("BD-"):
            return normalized_code
        if normalized_code.startswith("BD") and len(normalized_code) > 2:
            return f"BD-{normalized_code[2:]}"

    org_unit_name = _first_value(row, "organisation unit", "organization unit", "org unit", "ouname", "district", "name")
    if org_unit_name:
        normalized_name = normalize_org_unit_name(org_unit_name)
        if normalized_name in region_lookup:
            return region_lookup[normalized_name]

    raise ValueError(f"Could not resolve region_id from export row columns: {sorted(row.keys())}")


def parse_dhis2_label_export_row(
    row: Mapping[str, str],
    *,
    region_lookup: Mapping[str, str],
    label_source: str,
    case_threshold: int,
) -> LabelRecord:
    region_id = resolve_region_id_from_export_row(row, region_lookup=region_lookup)
    period = _first_value(row, "week_start_date", "period", "pe")
    value = _first_value(row, "case_count", "value")
    observed = _first_value(row, "label_observed_at", "last updated", "lastupdated", "created")
    if period is None or value is None:
        raise ValueError("DHIS2 export row must include period and value columns.")

    case_count = int(float(value.strip() or "0"))
    label_observed_at = None
    if observed:
        observed_token = observed.strip().replace("T", " ").split(" ")[0]
        try:
            label_observed_at = date.fromisoformat(observed_token)
        except ValueError:
            label_observed_at = None

    return LabelRecord(
        region_id=region_id,
        week_start_date=parse_period_to_week_start(period),
        label_event=case_count >= case_threshold,
        case_count=case_count,
        label_source=label_source,
        label_observed_at=label_observed_at,
    )


def aggregate_label_records(rows: list[LabelRecord]) -> list[LabelRecord]:
    grouped: dict[tuple[str, date, str], LabelRecord] = {}
    for row in rows:
        key = (row.region_id, row.week_start_date, row.label_source)
        existing = grouped.get(key)
        if existing is None:
            grouped[key] = row
            continue
        grouped[key] = LabelRecord(
            region_id=row.region_id,
            week_start_date=row.week_start_date,
            label_event=existing.label_event or row.label_event,
            case_count=(existing.case_count or 0) + (row.case_count or 0),
            label_source=row.label_source,
            label_observed_at=max(
                [candidate for candidate in [existing.label_observed_at, row.label_observed_at] if candidate is not None],
                default=None,
            ),
        )
    return sorted(grouped.values(), key=lambda item: (item.week_start_date, item.region_id, item.label_source))


def _persist_label_records(
    session: Session,
    rows: list[LabelRecord],
    *,
    source_name: str,
    upstream_asset_uri: str,
    checksum: str,
) -> IngestResult:
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
        upstream_asset_uri=upstream_asset_uri,
        record_count=len(rows),
        checksum=checksum,
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
        file_path=upstream_asset_uri,
        rows_read=len(rows),
        rows_inserted=inserted,
        rows_updated=updated,
    )


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

    return _persist_label_records(
        session,
        rows,
        source_name=source_name,
        upstream_asset_uri=str(path),
        checksum=file_checksum(path),
    )


def fetch_dhis2_label_export(config: RealLabelFeedConfig) -> tuple[str, str]:
    if not config.export_url:
        raise ValueError("ODSSWS_DHIS2_LABEL_EXPORT_URL is required for dhis2_csv_url mode.")

    auth = None
    if config.username and config.password:
        auth = (config.username, config.password)

    with httpx.Client(timeout=90.0, follow_redirects=True, auth=auth) as client:
        response = client.get(config.export_url)
        response.raise_for_status()
        content = response.text

    if "<html" in content[:200].lower():
        raise ValueError("DHIS2 export request returned HTML instead of CSV. Check credentials and export URL.")
    return config.export_url, content


def _write_label_export(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def _transform_dhis2_rows_to_records(
    session: Session,
    rows: list[dict[str, str]],
    *,
    config: RealLabelFeedConfig,
) -> list[LabelRecord]:
    region_lookup = build_region_lookup(session)
    records = [
        parse_dhis2_label_export_row(
            row,
            region_lookup=region_lookup,
            label_source=config.label_source,
            case_threshold=config.case_threshold,
        )
        for row in rows
    ]
    return aggregate_label_records(records)


def _preview_row_excerpt(row: Mapping[str, str], *, limit: int = 4) -> dict[str, str]:
    excerpt: dict[str, str] = {}
    for key in list(row.keys())[:limit]:
        excerpt[key] = row[key]
    return excerpt


def _load_real_label_export(config: RealLabelFeedConfig, *, labels_dir: Path) -> tuple[str, str, Path | None]:
    if config.mode == "standard_csv":
        if not config.export_path:
            raise ValueError("ODSSWS_DHIS2_LABEL_EXPORT_PATH is required for standard_csv mode.")
        path = Path(config.export_path).resolve()
        return str(path), path.read_text(encoding="utf-8"), path

    if config.mode == "dhis2_csv_url":
        upstream_asset_uri, content = fetch_dhis2_label_export(config)
        raw_export_path = _write_label_export(labels_dir / "dghs_dhis2_raw_export.csv", content)
        return upstream_asset_uri, content, raw_export_path

    if config.mode == "dhis2_csv_file":
        if not config.export_path:
            raise ValueError("ODSSWS_DHIS2_LABEL_EXPORT_PATH is required for dhis2_csv_file mode.")
        raw_export_path = Path(config.export_path).resolve()
        return str(raw_export_path), raw_export_path.read_text(encoding="utf-8"), raw_export_path

    raise ValueError(
        f"Unsupported real label mode '{config.mode}'. "
        "Expected dhis2_csv_url, dhis2_csv_file, or standard_csv."
    )


def _parse_real_label_export_rows(
    session: Session,
    rows: list[dict[str, str]],
    *,
    config: RealLabelFeedConfig,
) -> tuple[list[LabelRecord], list[LabelValidationIssue]]:
    issues: list[LabelValidationIssue] = []
    valid_records: list[LabelRecord] = []

    if config.mode == "standard_csv":
        parser = parse_label_csv_row
        parser_kwargs: dict[str, object] = {}
    else:
        parser = parse_dhis2_label_export_row
        parser_kwargs = {
            "region_lookup": build_region_lookup(session),
            "label_source": config.label_source,
            "case_threshold": config.case_threshold,
        }

    for row_number, row in enumerate(rows, start=2):
        try:
            record = parser(row, **parser_kwargs) if parser is parse_dhis2_label_export_row else parser(row)
        except Exception as exc:
            issues.append(
                LabelValidationIssue(
                    row_number=row_number,
                    message=str(exc),
                    row_excerpt=_preview_row_excerpt(row),
                )
            )
            continue
        valid_records.append(record)

    return aggregate_label_records(valid_records), issues


def validate_real_label_export(
    session: Session,
    *,
    config: RealLabelFeedConfig | None = None,
    write_normalized: bool = True,
) -> LabelValidationResult:
    resolved_config = config or load_real_label_feed_config()
    if resolved_config is None:
        raise ValueError(
            "Real label feed is not configured. Set ODSSWS_REAL_LABELS_MODE to "
            "'dhis2_csv_url', 'dhis2_csv_file', or 'standard_csv'."
        )

    labels_dir = data_dir() / "labels"
    upstream_asset_uri, content, _raw_export_path = _load_real_label_export(resolved_config, labels_dir=labels_dir)
    export_rows = list(csv.DictReader(io.StringIO(content)))
    if not export_rows:
        raise ValueError("Real label export produced no rows.")

    records, issues = _parse_real_label_export_rows(session, export_rows, config=resolved_config)
    normalized_path = None
    if write_normalized and records:
        normalized_path = str(write_records_to_csv(labels_dir / "dghs_dhis2_normalized_labels.csv", records))

    weeks = sorted({record.week_start_date for record in records})
    distinct_regions = len({record.region_id for record in records})
    return LabelValidationResult(
        label_source=resolved_config.label_source,
        upstream_asset_uri=upstream_asset_uri,
        rows_read=len(export_rows),
        valid_rows=len(export_rows) - len(issues),
        invalid_rows=len(issues),
        aggregated_rows=len(records),
        distinct_regions=distinct_regions,
        earliest_week=None if not weeks else weeks[0].isoformat(),
        latest_week=None if not weeks else weeks[-1].isoformat(),
        normalized_path=normalized_path,
        issues=issues,
    )


def ingest_real_labels(
    session: Session,
    *,
    config: RealLabelFeedConfig | None = None,
    source_name: str = "dghs_dhis2_labels",
) -> IngestResult:
    resolved_config = config or load_real_label_feed_config()
    if resolved_config is None:
        raise ValueError(
            "Real label feed is not configured. Set ODSSWS_REAL_LABELS_MODE to "
            "'dhis2_csv_url', 'dhis2_csv_file', or 'standard_csv'."
        )

    validation = validate_real_label_export(session, config=resolved_config, write_normalized=True)
    if validation.invalid_rows:
        first_issue = validation.issues[0]
        raise ValueError(
            f"Real label export validation failed with {validation.invalid_rows} invalid row(s). "
            f"First issue at row {first_issue.row_number}: {first_issue.message}"
        )

    labels_dir = data_dir() / "labels"
    upstream_asset_uri, _content, raw_export_path = _load_real_label_export(resolved_config, labels_dir=labels_dir)
    raw_checksum_path = raw_export_path if raw_export_path is not None else Path(upstream_asset_uri).resolve()
    normalized_path = Path(validation.normalized_path or labels_dir / "dghs_dhis2_normalized_labels.csv")
    records = [
        parse_label_csv_row(row)
        for row in csv.DictReader(io.StringIO(normalized_path.read_text(encoding="utf-8")))
    ]

    return _persist_label_records(
        session,
        records,
        source_name=source_name,
        upstream_asset_uri=upstream_asset_uri,
        checksum=file_checksum(raw_checksum_path),
    )


def write_records_to_csv(path: Path, rows: list[LabelRecord]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "region_id",
                "week_start_date",
                "label_event",
                "case_count",
                "label_source",
                "label_observed_at",
            ],
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "region_id": row.region_id,
                    "week_start_date": row.week_start_date.isoformat(),
                    "label_event": str(row.label_event).lower(),
                    "case_count": row.case_count,
                    "label_source": row.label_source,
                    "label_observed_at": None if row.label_observed_at is None else row.label_observed_at.isoformat(),
                }
            )
    return path
