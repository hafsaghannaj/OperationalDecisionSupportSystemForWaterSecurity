from collections.abc import Sequence
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from typing import Any


MODEL_FEATURE_COLUMNS: tuple[str, ...] = (
    "rainfall_total_mm_7d",
    "rainfall_anomaly_zscore",
    "population_total",
    "population_density_km2",
    "wash_access_basic_water_pct",
    "wash_access_basic_sanitation_pct",
    "lag_case_count_1w",
    "rolling_case_count_4w",
)


def build_logistic_baseline() -> Pipeline:
    """Return a pragmatic, inspectable baseline classifier."""
    return Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="median")),
            ("scaler", StandardScaler()),
            ("classifier", LogisticRegression(max_iter=1000, class_weight="balanced")),
        ]
    )


def build_lightgbm_baseline() -> Pipeline:
    """Return the first tree-based challenger model when LightGBM is installed."""
    from lightgbm import LGBMClassifier

    return Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="median")),
            (
                "classifier",
                LGBMClassifier(
                    n_estimators=160,
                    learning_rate=0.05,
                    num_leaves=15,
                    min_child_samples=5,
                    subsample=0.9,
                    colsample_bytree=0.9,
                    class_weight="balanced",
                    random_state=42,
                    verbosity=-1,
                ),
            ),
        ]
    )


def feature_vector(
    record: Any,
    *,
    feature_columns: Sequence[str] = MODEL_FEATURE_COLUMNS,
) -> list[float | int | None]:
    return [getattr(record, column) for column in feature_columns]
