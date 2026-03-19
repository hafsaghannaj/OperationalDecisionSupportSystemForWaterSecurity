import pytest

from pipelines.ingest.admin_boundaries import parse_boundary_csv_row
from pipelines.ingest.common import parse_bool
from pipelines.ingest.labels import parse_dhis2_label_export_row, parse_label_csv_row, parse_period_to_week_start


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


def test_parse_period_to_week_start_supports_dhis2_week_format() -> None:
    parsed = parse_period_to_week_start("2026W10")

    assert parsed.isoformat() == "2026-03-02"


def test_parse_dhis2_label_export_row_maps_org_unit_names() -> None:
    row = parse_dhis2_label_export_row(
        {
            "Organisation unit": "Khulna",
            "Period": "2026W10",
            "Value": "7",
        },
        region_lookup={"khulna": "BD-4047"},
        label_source="dghs_dhis2_weekly_cases",
        case_threshold=1,
    )

    assert row.region_id == "BD-4047"
    assert row.case_count == 7
    assert row.label_event is True
