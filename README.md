# AquaIntel

AquaIntel is an operational decision support system for water security. The MVP in this repo is scoped to weekly district-level outbreak risk scoring for a single pilot geography, exposed through an API and a map-first dashboard.

## Stack

- Python 3.12 with `uv`
- FastAPI for the API
- Prefect for scheduled flows
- PostgreSQL + PostGIS for geospatial storage
- scikit-learn and LightGBM for modeling
- Next.js + TypeScript for the web dashboard
- Docker Compose for local development

## Repository Layout

```text
services/api      FastAPI service
services/worker   Prefect-driven worker entrypoint
services/web      Next.js dashboard
pipelines/        Ingestion, feature, training, and scoring jobs
libs/             Shared schemas and utility code
docs/             Architecture, contracts, and operating notes
tests/            API and pipeline tests
```

## Quick Start

### 1. Install dependencies

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
cd services/web && npm install
```

If you install Python dependencies on the host instead of in Docker, geospatial packages such as `geopandas` and `rasterio` may require GDAL and PROJ system libraries.

For the optional heavier analytics stack later in the project:

```bash
.venv/bin/pip install -e '.[dev,geo,ml]'
```

### 2. Start the local stack

```bash
make dev
```

This brings up:

- PostGIS on `localhost:5432`
- API on `http://localhost:8000`
- Web dashboard on `http://localhost:3000`

### 3. Apply database migrations

Once the database is running, apply the initial schema:

```bash
make migrate
```

If you are running the stack directly on the host instead of through Docker:

```bash
make migrate-local
```

### 4. Load sample reference data

This repo includes illustrative seed data for local development. The bootstrap flow now also trains and promotes a baseline model artifact before it writes risk scores:

```bash
make seed
```

If you are running directly on the host:

```bash
make seed-local
```

### 5. Retrain the baseline model

If you want to retrain against the current database contents without reseeding:

```bash
make train
```

If you are running directly on the host:

```bash
make train-local
```

### 6. Run services without Docker

```bash
make api
make worker
make web
```

## Current Status

This is the initial scaffold. The repo includes:

- a concrete MVP build plan in [BUILD_PLAN.md](/Users/hafsaghannaj/OperationalDecisionSupportSystemForWaterSecurity/BUILD_PLAN.md)
- a database-backed API surface for regions, risk, drivers, and alerts
- a model status endpoint for the currently active scoring path
- a first worker flow that sequences ingest, feature, and scoring steps
- boundary and historical label ingesters with source-run tracking
- feature construction plus forward-chaining baseline model training with promoted artifacts
- a multi-model training path that compares logistic regression against an optional LightGBM challenger
- promotion gates that require the trained model to beat the persistence baseline before activation
- a model-run registry with explicit champion/challenger states and manual promotion controls
- model cards generated for promoted artifacts
- scoring that uses the promoted model when present, with calibrated alert thresholds from validation metadata
- freshness guardrails for training inputs and scoring windows, surfaced in model metadata
- drift checks that compare the live scoring window to the stored training feature profile
- a scoring-run registry with alert-volume monitoring and latest-run health surfaced in the dashboard
- a dashboard shell that matches the planned operator workflow

## Next Build Steps

1. Lock the pilot geography, outcome, and label source.
2. Add retraining scheduling and approval logging around the manual promotion step.
3. Add operator acknowledgment logging before field deployment.
4. Add a field-action audit trail that links alerts, acknowledgments, and follow-up outcomes.
