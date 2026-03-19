from __future__ import annotations

from datetime import date
import re


WEEK_PATTERN = re.compile(r"(?P<year>\d{4})-W(?P<week>\d{2})$")


def format_week_string(value: date) -> str:
    iso_year, iso_week, _iso_weekday = value.isocalendar()
    return f"{iso_year}-W{iso_week:02d}"


def parse_week_string(value: str) -> date:
    match = WEEK_PATTERN.fullmatch(value)
    if not match:
        raise ValueError("Week must use ISO format YYYY-Www, for example 2026-W11.")

    year = int(match.group("year"))
    week = int(match.group("week"))
    return date.fromisocalendar(year, week, 1)
