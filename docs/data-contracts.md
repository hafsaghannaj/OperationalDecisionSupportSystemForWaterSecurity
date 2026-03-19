# Data Contracts

## District-Week Feature Contract

Each row represents one administrative unit for one epidemiological week.

The current implementation stores covariates and lag features in `district_week_features`, while labels remain in `district_week_labels` and are joined on `region_id` and `week_start_date` during training and evaluation.

### Required keys

- `region_id`
- `region_name`
- `week_start_date`
- `country_code`
- `admin_level`

### Required label fields

- `label_event`
- `label_source`
- `label_observed_at`

### Required weather fields

- `rainfall_total_mm_7d`
- `rainfall_anomaly_zscore`

### Required exposure fields

- `population_total`
- `population_density_km2`
- `wash_access_basic_water_pct`
- `wash_access_basic_sanitation_pct`

### Required metadata

- `source_run_id`
- `feature_build_version`
- `quality_flag`

### Derived lag features

- `lag_case_count_1w`
- `rolling_case_count_4w`

## Source Run Contract

Every pipeline run should record:

- source name
- execution timestamp
- upstream asset URI
- record count
- checksum or version
- status
