from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
from pathlib import Path

from sqlalchemy.orm import Session

from services.api.app.db_models import SourceRun


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def sample_data_dir() -> Path:
    return repo_root() / "sample_data"


def file_checksum(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8192), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_bool(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"1", "true", "t", "yes", "y"}:
        return True
    if normalized in {"0", "false", "f", "no", "n"}:
        return False
    raise ValueError(f"Cannot parse boolean value '{value}'.")


@dataclass(slots=True)
class IngestResult:
    source_name: str
    source_run_id: str
    file_path: str
    rows_read: int
    rows_inserted: int
    rows_updated: int

    def as_dict(self) -> dict[str, str | int]:
        return asdict(self)

    def summary(self) -> str:
        return (
            f"{self.source_name}: read {self.rows_read} rows from {self.file_path}, "
            f"inserted {self.rows_inserted}, updated {self.rows_updated}."
        )


def create_source_run(
    session: Session,
    *,
    source_name: str,
    upstream_asset_uri: str,
    record_count: int,
    checksum: str,
) -> SourceRun:
    source_run = SourceRun(
        source_name=source_name,
        upstream_asset_uri=upstream_asset_uri,
        record_count=record_count,
        checksum=checksum,
        status="success",
    )
    session.add(source_run)
    session.flush()
    return source_run
