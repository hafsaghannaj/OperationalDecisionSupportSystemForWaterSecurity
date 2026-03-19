from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def pilot_definition_path() -> Path:
    return repo_root() / "config" / "pilot_definition.json"


@lru_cache
def load_pilot_definition() -> dict[str, Any]:
    return json.loads(pilot_definition_path().read_text(encoding="utf-8"))


def pilot_geography_label() -> str:
    pilot = load_pilot_definition()
    return f"{pilot['country']} {pilot['admin_level_label']} pilot ({pilot['admin_level']})"


def pilot_outcome_name() -> str:
    return str(load_pilot_definition()["outcome_name"])


def pilot_prediction_horizon() -> str:
    return str(load_pilot_definition()["prediction_horizon"])


def pilot_intended_users_text() -> str:
    users = load_pilot_definition()["intended_users"]
    return ", ".join(str(user) for user in users)


def write_real_data_manifest(output_path: Path | None = None) -> Path:
    pilot = load_pilot_definition()
    destination = output_path or (repo_root() / "data" / "pilot" / "real_data_manifest.json")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(pilot, indent=2), encoding="utf-8")
    return destination


def load_demo_risk_points(path: Path | None = None) -> list[dict[str, Any]]:
    source = path or (repo_root() / "data" / "risk_scored_points.json")
    return json.loads(source.read_text(encoding="utf-8"))
