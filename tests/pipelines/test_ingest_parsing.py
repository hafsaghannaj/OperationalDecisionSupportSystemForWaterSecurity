import pytest

from pipelines.ingest.admin_boundaries import parse_boundary_csv_row
from pipelines.ingest.common import parse_bool
from pipelines.ingest.labels import (
    RealLabelFeedConfig,
    parse_dhis2_label_export_row,
    parse_label_csv_row,
    parse_period_to_week_start,
    validate_real_label_export,
)


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


def test_validate_real_label_export_reports_invalid_standard_csv_rows(tmp_path) -> None:
    export_path = tmp_path / "labels.csv"
    export_path.write_text(
        "\n".join(
            [
                "region_id,week_start_date,label_event,case_count,label_source,label_observed_at",
                "BD-10,2026-03-09,true,7,dghs_dhis2_weekly_cases,2026-03-15",
                "BD-20,2026-03-09,,3,dghs_dhis2_weekly_cases,2026-03-15",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    result = validate_real_label_export(
        session=object(),  # standard_csv validation does not consult the database
        config=RealLabelFeedConfig(
            mode="standard_csv",
            label_source="dghs_dhis2_weekly_cases",
            case_threshold=1,
            export_path=str(export_path),
        ),
        write_normalized=False,
    )

    assert result.rows_read == 2
    assert result.valid_rows == 1
    assert result.invalid_rows == 1
    assert result.aggregated_rows == 1
    assert result.earliest_week == "2026-03-09"
    assert result.issues[0].row_number == 3
