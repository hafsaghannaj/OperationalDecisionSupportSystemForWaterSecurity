# OperationalDecisionSupportSystemForWaterSecurity MVP Build Plan

Date: 2026-03-19

## 1. Product Decision

Build OperationalDecisionSupportSystemForWaterSecurity as a focused operational decision support MVP, not as a general water intelligence platform.

### MVP outcome

Deliver a weekly district-level outbreak risk product for one pilot geography, with:

- a probability score for the next 1 to 2 weeks
- interpretable drivers for each alert
- a map-first dashboard and API
- an auditable weekly scoring pipeline

### Default pilot assumption

Use cholera or acute watery diarrhea as the first outcome, with Bangladesh as the default pilot candidate.

This assumption is only valid if Phase 0 confirms access to district-level labels with enough history. If that fails, switch geography or outcome before building further.

### Locked pilot definition

The repo now locks the implementation target in `config/pilot_definition.json`:

- geography: Bangladesh
- admin level: ADM2 districts
- outcome: weekly cholera or acute watery diarrhea escalation risk
- target label path: DGHS or partner surveillance feed, with bundled proxy labels retained only for local development

### Non-goals for MVP

- no multi-country rollout
- no sensor network deployment
- no patient-level data ingestion
- no pathogen detection from imagery
- no physics-informed, federated, or graph models in v1
- no commercial imagery dependency

## 2. First Constraint To Resolve

This folder is currently not a standalone git repository. Git resolves upward to `/Users/hafsaghannaj`, so repo-wide commands here would affect the home-level worktree.

Before implementation starts:

1. create a dedicated repo for OperationalDecisionSupportSystemForWaterSecurity at this path
2. add a project README, license, and `.gitignore`
3. keep all project automation scoped to this repo only

Do not skip this. Otherwise the build becomes hard to isolate, review, and deploy.

## 3. Phase-0 Go/No-Go Gate

Do not build pipelines or models until these four items are confirmed.

### Required decisions

- Pilot geography and admin level are fixed.
- Outcome definition is fixed.
- A data owner or public source for labels is identified.
- A partner decision loop exists for acting on alerts.

### Required assets

- 24+ months of historical labels at the chosen admin/time grain
- boundary files for the chosen geography
- one static exposure layer
- one dynamic weather or hydrology layer

### Go criteria

Proceed only if OperationalDecisionSupportSystemForWaterSecurity can assemble a district-by-week training table with enough non-null labels to evaluate a baseline model honestly.

### No-go criteria

If subnational labels are not available, do not fake precision. Either:

- pivot to a coarser admin level
- use a partner-provided proxy outcome
- switch the pilot geography

## 4. Recommended MVP Scope

### Time grain

Weekly.

### Spatial grain

District or equivalent admin unit.

### Prediction horizon

1 to 2 weeks ahead.

### Users

- WASH operations leads
- public health surveillance teams
- humanitarian coordination teams

### Core questions the product must answer

- Which districts need review this week?
- Why is risk elevated there?
- How certain is the alert?
- What changed since last week?

## 5. Recommended Technical Stack

Choose a stack that is boring, inspectable, and deployable by a small team.

### Backend and data

- Python 3.12
- `uv` for dependency management
- FastAPI for the serving API
- PostgreSQL + PostGIS for relational and geospatial storage
- object storage for raw rasters and extracts
- Prefect for scheduled data and scoring flows
- MLflow for model registry and experiment tracking

### Modeling

- pandas / geopandas / xarray / rasterio for data prep
- scikit-learn for baselines and evaluation
- LightGBM or XGBoost for the first production model

### Frontend

- Next.js
- TypeScript
- MapLibre GL for maps
- a small charting library for time series and uncertainty bands

### Local development

- Docker Compose
- one command to start database, API, worker, and frontend

### Cloud target

Use one cloud provider only for MVP. Preferred pattern:

- managed Postgres/PostGIS
- managed object storage
- containerized API and worker services
- scheduled jobs for weekly refresh
- centralized logs and metrics

## 6. Proposed Repository Layout

```text
OperationalDecisionSupportSystemForWaterSecurity/
  BUILD_PLAN.md
  README.md
  .gitignore
  docker-compose.yml
  Makefile
  docs/
    architecture.md
    data-contracts.md
    model-card-template.md
    runbooks/
  services/
    api/
    web/
    worker/
  pipelines/
    ingest/
    features/
    training/
    scoring/
  libs/
    schemas/
    geo/
    ml/
  infra/
    docker/
    terraform/
  tests/
    integration/
    pipelines/
    api/
```

## 7. MVP Data Plan

Keep the first feature set small. Build the district-by-week training table first, then expand only if it improves forward validation.

### Required inputs for v1

- admin boundaries for the pilot geography
- population exposure from WorldPop
- WASH access indicators from JMP
- precipitation from IMERG
- historical outcome labels from WHO, GTFCC, ministry, or partner source

### Optional but useful v1.1 inputs

- flood or wetness proxy derived from Sentinel-1
- seasonality features
- lagged case counts

### Phase-2 inputs only

- GRACE or drought indicators
- chlorophyll or coastal ecology signals
- GEMStat-derived validation streams
- commercial imagery
- IoT sensor feeds

### Core data model

The database should support these tables from the beginning:

- `admin_boundaries`
- `raw_assets`
- `source_runs`
- `district_week_features`
- `district_week_labels`
- `model_runs`
- `risk_scores`
- `alert_events`

## 8. Model Strategy

### Baseline model

Start with a binary probabilistic classifier for outbreak risk.

Recommended first feature families:

- recent rainfall totals and anomalies
- rolling flood or wetness proxy
- static WASH access variables
- population density or exposed population
- seasonality terms
- lagged outcome values, if allowed by the label cadence

### Evaluation protocol

Use deployment-shaped validation:

- forward-chaining time splits
- at least one spatial holdout sensitivity test
- calibration analysis
- precision/recall across alert thresholds

### Baselines to beat

- seasonal naive baseline
- persistence baseline using recent labels only
- simple logistic regression

### MVP success criteria

- better AUCPR than the persistence baseline
- usable calibration after post-training calibration if needed
- alert lead time acceptable to the pilot partner
- interpretable feature contribution view per district-week

## 9. Delivery Architecture

### Data flow

1. scheduled ingestion pulls raw source files and metadata
2. normalization jobs align everything to the district-week data spine
3. feature jobs create model-ready tables
4. training flow retrains on schedule or by approval
5. scoring flow produces weekly risk outputs
6. API serves latest and historical outputs
7. dashboard displays map, drivers, history, and uncertainty

### Minimum API surface

- `GET /health`
- `GET /regions`
- `GET /risk/latest`
- `GET /risk/history`
- `GET /drivers/{region_id}/{week}`
- `GET /alerts`

### Minimum dashboard views

- latest district risk map
- district detail page with trend and drivers
- last-update timestamp and data freshness
- filter by admin region and week
- export of alert table as CSV

## 10. MLOps And Operations Requirements

These are part of the MVP, not post-MVP cleanup.

### Required operational controls

- versioned datasets and model artifacts
- reproducible training runs
- automated weekly scoring
- data freshness checks
- missingness and schema validation
- drift monitoring on key features
- runbook for failed weekly jobs

### Minimum governance controls

- no person-level PII in the MVP database
- role-based access for admin actions
- secrets stored outside source control
- model card for each promoted model
- alert text must include uncertainty and recommended human review

## 11. Execution Plan

Plan for a 16-week MVP build with explicit gates.

### Phase 0: Pilot Lock And Data Access
Duration: 2 weeks

Deliverables:

- pilot geography and outcome finalized
- label source confirmed
- boundary source confirmed
- decision memo defining admin grain, cadence, horizon, and users

Exit criteria:

- one approved product brief
- one sample district-week label extract
- one signed-off MVP scope

### Phase 1: Repo Bootstrap And Data Spine
Duration: 2 weeks

Deliverables:

- standalone repo initialized
- local dev stack running with Docker Compose
- PostGIS schema created
- first normalized admin boundary table loaded
- data contracts written for each source

Exit criteria:

- `make dev` starts the local stack
- one boundary dataset and one static exposure dataset loaded end-to-end

### Phase 2: Ingestion And Feature Pipelines
Duration: 3 weeks

Deliverables:

- IMERG ingestion flow
- label ingestion flow
- WorldPop and JMP loaders
- district-week feature aggregation jobs
- data quality checks on every pipeline

Exit criteria:

- a reproducible district-week feature table exists
- backfill runs for the historical window complete without manual edits

### Phase 3: Baseline Modeling
Duration: 3 weeks

Deliverables:

- baseline modeling notebook or script converted into production code
- forward-validation report
- calibration report
- feature importance or SHAP-based driver output
- first model registered in MLflow

Exit criteria:

- model beats naive baselines
- evaluation results are documented and reviewable

### Phase 4: API And Dashboard
Duration: 3 weeks

Deliverables:

- API endpoints serving latest and historical risk scores
- dashboard with risk map and district drill-down
- CSV export for alert list
- auth for internal pilot users

Exit criteria:

- a user can view weekly outputs without touching notebooks or databases

### Phase 5: Operational Hardening
Duration: 3 weeks

Deliverables:

- weekly automated scoring schedule
- alerting for failed runs and stale data
- runbook for support and incident response
- model card and pilot usage guide

Exit criteria:

- two consecutive dry-run weekly cycles succeed on schedule

## 12. Initial Backlog

These are the first tickets to create once the repo exists.

### P0

- Initialize standalone git repository and developer bootstrap files.
- Write the product brief with admin level, outcome, horizon, and user roles.
- Acquire pilot boundary files and load them into PostGIS.
- Define the district-week data contract.
- Implement source metadata tracking in `source_runs` and `raw_assets`.
- Ingest one historical label extract and validate null coverage.

### P1

- Implement IMERG ingestion and district aggregation.
- Load WorldPop and aggregate to district level.
- Load JMP and join to district metadata.
- Create the first `district_week_features` build job.
- Add schema and freshness checks.
- Create baseline persistence and logistic regression evaluators.

### P2

- Train LightGBM baseline.
- Register the first model.
- Build `/risk/latest` and `/drivers/{region_id}/{week}` endpoints.
- Build the initial web dashboard shell.
- Add weekly scoring automation.

## 13. Minimum Team

This MVP can be built by a small cross-functional team:

- 1 technical lead or product engineer
- 1 data engineer with geospatial pipeline experience
- 1 ML engineer or applied scientist
- 1 frontend engineer
- 1 part-time domain advisor from WASH or public health

One person can cover multiple roles, but data engineering and domain validation cannot be omitted.

## 14. Major Risks And Mitigations

### Risk: labels are too sparse or too delayed

Mitigation:

- make label access the first gate
- allow fallback to coarser geography or proxy outcome

### Risk: remote sensing feature work becomes the schedule sink

Mitigation:

- start with district aggregates from a minimal set of sources
- defer chlorophyll, groundwater, and complex SAR workflows

### Risk: a technically good model is not operationally useful

Mitigation:

- require partner-defined lead time and action thresholds early
- optimize dashboard and alert text for decisions, not ML elegance

### Risk: the weekly system is brittle

Mitigation:

- treat data quality, retries, monitoring, and runbooks as MVP work

## 15. Definition Of Done For MVP

The MVP is done when all of the following are true:

- OperationalDecisionSupportSystemForWaterSecurity generates weekly district-level risk scores for the pilot region.
- A user can review risk, drivers, and history in the dashboard.
- The scoring pipeline is automated and monitored.
- The model is versioned and its validation report is documented.
- A pilot partner can state what action each alert is meant to trigger.

## 16. Recommended Next Move

Do these three things before writing application code:

1. lock the pilot geography, outcome, and label source
2. initialize this folder as a standalone repo
3. create the district-week data contract and sample training extract

If those three items are completed, implementation can start immediately with Phase 1.
