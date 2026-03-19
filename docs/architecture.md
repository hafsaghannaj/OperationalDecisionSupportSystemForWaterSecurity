# Architecture

## Planes

AquaIntel is organized into four planes:

1. Ingestion: source pullers for labels, weather, and exposure layers.
2. Storage: PostGIS tables for district-week data plus object storage for raw assets.
3. Modeling: feature builders, baseline training, model registration, and scoring.
4. Delivery: FastAPI endpoints and the operator dashboard.

## Initial Runtime Topology

- `db`: PostgreSQL + PostGIS
- `api`: serves risk, regions, drivers, and alerts
- `worker`: runs weekly ingest, feature, and scoring flows
- `web`: operator-facing dashboard

## Data Spine

The core data spine is district-by-week. Every dynamic input should be transformed to:

- `region_id`
- `week_start_date`
- feature columns
- source metadata
- quality flags

## MVP Principle

The system should remain simple until the district-week feature table and baseline model are stable. No advanced modeling or complex sensor integration belongs in the first release.

