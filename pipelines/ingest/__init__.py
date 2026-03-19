"""Ingestion jobs."""

from pipelines.ingest.admin_boundaries import ingest_admin_boundaries_from_csv
from pipelines.ingest.labels import ingest_historical_labels_from_csv

__all__ = ["ingest_admin_boundaries_from_csv", "ingest_historical_labels_from_csv"]
