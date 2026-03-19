import pytest

from pipelines.ingest.admin_boundaries import parse_boundary_csv_row
from pipelines.ingest.common import parse_bool
from pipelines.ingest.labels import parse_label_csv_row


def test_parse_boundary_csv_row() -> None:
    row = parse_boundary_csv_row(
        {
            "region_id": "BD-10",
            "name": "Khulna",
            "country_code": "BD",
            "admin_level": "2",
            "geometry_wkt": "MULTIPOLYGON (((0 0, 1 0, 1 1, 0 1, 0 0)))",
        }
    )

    assert row.region_id == "BD-10"
    assert row.admin_level == 2


def test_parse_label_csv_row() -> None:
    row = parse_label_csv_row(
        {
            "region_id": "BD-10",
            "week_start_date": "2026-03-09",
            "label_event": "true",
            "case_count": "24",
            "label_source": "sample_surveillance",
            "label_observed_at": "2026-03-15",
        }
    )

    assert row.label_event is True
    assert row.case_count == 24
    assert row.week_start_date.isoformat() == "2026-03-09"


@pytest.mark.parametrize(("raw", "expected"), [("true", True), ("FALSE", False), ("1", True), ("0", False)])
def test_parse_bool(raw: str, expected: bool) -> None:
    assert parse_bool(raw) is expected


def test_parse_bool_rejects_unknown_value() -> None:
    with pytest.raises(ValueError):
        parse_bool("maybe")
