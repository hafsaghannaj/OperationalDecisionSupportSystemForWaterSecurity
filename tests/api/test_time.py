from datetime import date

from services.api.app.time import format_week_string, parse_week_string


def test_format_week_string() -> None:
    assert format_week_string(date(2026, 3, 16)) == "2026-W12"


def test_parse_week_string() -> None:
    assert parse_week_string("2026-W12") == date(2026, 3, 16)
