import json

from outbreaks.demo import build_demo_outputs


def test_build_demo_outputs_writes_expected_files(tmp_path) -> None:
    results_dir = tmp_path / "results"
    data_dir = tmp_path / "data"
    site_path = tmp_path / "index.html"

    summary = build_demo_outputs(
        results_dir=results_dir,
        data_dir=data_dir,
        site_path=site_path,
    )

    assert summary["model_family"]
    assert (results_dir / "synthetic_training_data.csv").exists()
    assert (results_dir / "model_report.json").exists()
    assert (results_dir / "risk_scored_points.csv").exists()
    assert (results_dir / "risk_map.html").exists()
    assert (data_dir / "risk_scored_points.json").exists()
    assert site_path.exists()

    payload = json.loads((data_dir / "risk_scored_points.json").read_text(encoding="utf-8"))
    assert payload[0]["location_label"] == "Khulna"
    assert payload[0]["region_id"] == "BD-4047"
