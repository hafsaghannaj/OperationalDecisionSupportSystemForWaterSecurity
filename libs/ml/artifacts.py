from __future__ import annotations

import hashlib
import json
import pickle
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from libs.ml.baselines import MODEL_FEATURE_COLUMNS


def _sha256_file(path: Path) -> str:
    """Return the hex SHA-256 digest of a file."""
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65_536), b""):
            h.update(chunk)
    return h.hexdigest()


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def model_artifact_dir(output_dir: str | Path | None = None) -> Path:
    if output_dir is not None:
        return Path(output_dir).resolve()
    return repo_root() / "artifacts" / "models"


def latest_metadata_path(output_dir: str | Path | None = None) -> Path:
    return model_artifact_dir(output_dir) / "latest.json"


def latest_model_card_path(output_dir: str | Path | None = None) -> Path:
    return model_artifact_dir(output_dir) / "latest-model-card.md"


@dataclass(slots=True)
class PromotedModel:
    model_version: str
    estimator: Any
    feature_columns: tuple[str, ...]
    metadata: dict[str, Any]
    model_path: Path
    metadata_path: Path


def persist_model_artifact(
    estimator: Any,
    metadata: Mapping[str, Any],
    *,
    output_dir: str | Path | None = None,
    promote: bool = False,
) -> tuple[Path, Path]:
    artifact_dir = model_artifact_dir(output_dir)
    artifact_dir.mkdir(parents=True, exist_ok=True)

    model_version = str(metadata["model_version"])
    model_path = artifact_dir / f"{model_version}.pkl"
    metadata_path = artifact_dir / f"{model_version}.json"

    with model_path.open("wb") as handle:
        pickle.dump(estimator, handle)

    payload = dict(metadata)
    payload["model_sha256"] = _sha256_file(model_path)
    payload["model_path"] = str(model_path)
    payload["metadata_path"] = str(metadata_path)

    metadata_json = json.dumps(payload, indent=2, sort_keys=True)
    metadata_path.write_text(f"{metadata_json}\n", encoding="utf-8")
    if promote:
        latest_metadata_path(output_dir).write_text(f"{metadata_json}\n", encoding="utf-8")
    return model_path, metadata_path


def persist_promoted_model(
    estimator: Any,
    metadata: Mapping[str, Any],
    *,
    output_dir: str | Path | None = None,
) -> tuple[Path, Path]:
    return persist_model_artifact(estimator, metadata, output_dir=output_dir, promote=True)


def load_promoted_model(*, metadata_path: str | Path | None = None) -> PromotedModel | None:
    resolved_metadata_path = (
        Path(metadata_path).resolve() if metadata_path is not None else latest_metadata_path().resolve()
    )
    if not resolved_metadata_path.exists():
        return None

    metadata = json.loads(resolved_metadata_path.read_text(encoding="utf-8"))
    model_path = Path(metadata["model_path"]).resolve()
    if not model_path.exists():
        return None

    expected_sha256 = metadata.get("model_sha256")
    if expected_sha256:
        actual_sha256 = _sha256_file(model_path)
        if actual_sha256 != expected_sha256:
            raise ValueError(
                f"Model integrity check failed for {model_path}: "
                f"expected {expected_sha256}, got {actual_sha256}. "
                "The artifact may have been tampered with."
            )

    with model_path.open("rb") as handle:
        estimator = pickle.load(handle)

    feature_columns = tuple(metadata.get("feature_columns") or MODEL_FEATURE_COLUMNS)
    return PromotedModel(
        model_version=str(metadata["model_version"]),
        estimator=estimator,
        feature_columns=feature_columns,
        metadata=metadata,
        model_path=model_path,
        metadata_path=resolved_metadata_path,
    )
