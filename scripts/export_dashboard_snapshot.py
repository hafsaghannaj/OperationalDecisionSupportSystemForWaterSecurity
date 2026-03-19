from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib import error, parse, request


OPTIONAL_STATUS_CODES = {404, 503}


def fetch_json(api_base: str, path: str, *, optional: bool = False):
    url = f"{api_base.rstrip('/')}{path}"
    try:
        with request.urlopen(url) as response:
            return json.load(response)
    except error.HTTPError as exc:
        if optional and exc.code in OPTIONAL_STATUS_CODES:
            return None
        raise RuntimeError(f"Request failed for {path}: {exc.code}") from exc
    except error.URLError as exc:
        raise RuntimeError(f"Request failed for {path}: {exc.reason}") from exc


def build_snapshot(api_base: str) -> dict[str, object]:
    regions = fetch_json(api_base, "/regions")
    latest_risk = fetch_json(api_base, "/risk/latest")
    snapshot = {
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "source_api_base": api_base.rstrip("/"),
        "regions": regions,
        "risk_latest": latest_risk,
        "alerts": fetch_json(api_base, "/alerts"),
        "data_quality": fetch_json(api_base, "/data/quality"),
        "model_status": fetch_json(api_base, "/model/status", optional=True),
        "model_compare": fetch_json(api_base, "/model/compare", optional=True),
        "scoring_health": fetch_json(api_base, "/scoring/health", optional=True),
        "audit_logs": fetch_json(api_base, "/audit/logs", optional=True) or [],
        "pilot": fetch_json(api_base, "/pilot", optional=True),
        "demo_risk_points": fetch_json(api_base, "/demo/risk-points", optional=True) or [],
        "regions_geojson": fetch_json(api_base, "/regions/geojson", optional=True),
        "risk_history_by_region": {},
        "drivers_by_region_week": {},
    }

    for risk_row in latest_risk:
        region_id = str(risk_row["region_id"])
        week = str(risk_row["week"])
        encoded_region_id = parse.quote(region_id, safe="")
        encoded_week = parse.quote(week, safe="")
        snapshot["risk_history_by_region"][region_id] = fetch_json(
            api_base,
            f"/risk/history?region_id={encoded_region_id}",
            optional=True,
        ) or []
        snapshot["drivers_by_region_week"][f"{region_id}:{week}"] = fetch_json(
            api_base,
            f"/drivers/{encoded_region_id}/{encoded_week}",
            optional=True,
        )

    return snapshot


def main() -> int:
    parser = argparse.ArgumentParser(description="Export a static dashboard snapshot from the API.")
    parser.add_argument("--api-base", default="http://127.0.0.1:8000", help="Base URL of the API to snapshot.")
    parser.add_argument(
        "--out",
        default="data/dashboard_snapshot.json",
        help="Path to write the snapshot JSON.",
    )
    args = parser.parse_args()

    snapshot = build_snapshot(args.api_base)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(snapshot, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {out_path} with {len(snapshot['risk_latest'])} risk rows.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
