from datetime import date
from pathlib import Path

from libs.ml.artifacts import load_promoted_model
from libs.ml.baselines import build_logistic_baseline
from libs.ml.freshness import FreshnessPolicy
from pipelines.training.baseline import (
    ModelCandidate,
    PromotionPolicy,
    TrainingExample,
    build_forward_chaining_splits,
    train_baseline_from_examples,
)
from sklearn.dummy import DummyClassifier
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline


def sample_training_examples() -> list[TrainingExample]:
    return [
        TrainingExample("BD-10", date(2026, 2, 16), True, None, 41.0, -1.3, 2680000.0, 1180.0, 78.0, 62.0, None, None, "ok"),
        TrainingExample("BD-20", date(2026, 2, 16), False, None, 36.0, -1.1, 2330000.0, 1040.0, 81.0, 68.0, None, None, "ok"),
        TrainingExample("BD-30", date(2026, 2, 16), False, None, 22.0, -1.0, 12400000.0, 4200.0, 92.0, 84.0, None, None, "ok"),
        TrainingExample("BD-10", date(2026, 2, 23), True, True, 58.0, -0.4, 2680000.0, 1180.0, 78.0, 62.0, 12, 12, "ok"),
        TrainingExample("BD-20", date(2026, 2, 23), False, False, 44.0, -0.3, 2330000.0, 1040.0, 81.0, 68.0, 3, 3, "ok"),
        TrainingExample("BD-30", date(2026, 2, 23), False, False, 27.0, -0.2, 12400000.0, 4200.0, 92.0, 84.0, 1, 1, "ok"),
        TrainingExample("BD-10", date(2026, 3, 2), True, True, 73.0, 0.5, 2680000.0, 1180.0, 78.0, 62.0, 16, 28, "ok"),
        TrainingExample("BD-20", date(2026, 3, 2), True, False, 57.0, 0.7, 2330000.0, 1040.0, 81.0, 68.0, 4, 7, "ok"),
        TrainingExample("BD-30", date(2026, 3, 2), False, False, 31.0, 0.4, 12400000.0, 4200.0, 92.0, 84.0, 1, 2, "ok"),
        TrainingExample("BD-10", date(2026, 3, 9), True, True, 89.0, 1.2, 2680000.0, 1180.0, 78.0, 62.0, 19, 47, "ok"),
        TrainingExample("BD-20", date(2026, 3, 9), True, True, 69.0, 1.1, 2330000.0, 1040.0, 81.0, 68.0, 7, 14, "ok"),
        TrainingExample("BD-30", date(2026, 3, 9), False, False, 35.0, 0.8, 12400000.0, 4200.0, 92.0, 84.0, 2, 4, "ok"),
    ]


def test_build_forward_chaining_splits() -> None:
    splits = build_forward_chaining_splits(sample_training_examples(), min_train_weeks=2)

    assert len(splits) == 2
    assert len(splits[0][0]) == 6
    assert len(splits[0][1]) == 3
    assert splits[1][1][0].week_start_date == date(2026, 3, 9)


def test_train_baseline_from_examples_persists_challenger_artifact(tmp_path) -> None:
    result = train_baseline_from_examples(
        sample_training_examples(),
        feature_build_version="sample-v1",
        label_sources=["sample_surveillance"],
        output_dir=tmp_path,
        min_train_weeks=2,
    )

    promoted_model = load_promoted_model(metadata_path=tmp_path / "latest.json")

    assert result.model_version.startswith("baseline-logreg-")
    assert result.training_rows == 12
    assert result.training_weeks == 4
    assert result.evaluation_splits == 2
    assert result.promotion_status == "eligible"
    assert result.promoted_at is None
    assert result.evaluation.average_precision is not None
    assert result.model_card_path is not None
    assert result.model_family == "logistic_regression"
    assert any(candidate.status == "selected" for candidate in result.candidate_results)
    assert promoted_model is None
    metadata = Path(result.metadata_path).read_text(encoding="utf-8")
    assert '"feature_build_version": "sample-v1"' in metadata
    assert '"promotion_status": "eligible"' in metadata
    assert '"registry_status": "challenger"' in metadata
    assert Path(result.model_card_path).exists()
    assert "Promotion date: Not promoted" in Path(result.model_card_path).read_text(encoding="utf-8")


def test_train_baseline_from_examples_rejects_when_policy_not_met(tmp_path) -> None:
    result = train_baseline_from_examples(
        sample_training_examples(),
        feature_build_version="sample-v1",
        label_sources=["sample_surveillance"],
        output_dir=tmp_path,
        min_train_weeks=2,
        promotion_policy=PromotionPolicy(min_average_precision=1.01),
    )

    assert result.promotion_status == "rejected"
    assert result.promoted_at is None
    assert result.model_card_path is None
    assert result.promotion_reasons
    assert not (tmp_path / "latest.json").exists()
    assert Path(result.metadata_path).exists()


def build_dummy_candidate() -> Pipeline:
    return Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="median")),
            ("classifier", DummyClassifier(strategy="prior")),
        ]
    )


def test_train_baseline_from_examples_selects_best_candidate(tmp_path) -> None:
    result = train_baseline_from_examples(
        sample_training_examples(),
        feature_build_version="sample-v1",
        label_sources=["sample_surveillance"],
        output_dir=tmp_path,
        min_train_weeks=2,
        candidate_specs=[
            ModelCandidate(model_family="logistic_regression", build_estimator=build_logistic_baseline),
            ModelCandidate(model_family="dummy_prior", build_estimator=build_dummy_candidate),
        ],
    )

    candidate_by_family = {candidate.model_family: candidate for candidate in result.candidate_results}

    assert result.model_family == "logistic_regression"
    assert candidate_by_family["logistic_regression"].status == "selected"
    assert candidate_by_family["dummy_prior"].status == "evaluated"
    assert candidate_by_family["dummy_prior"].evaluation is not None
    assert candidate_by_family["logistic_regression"].evaluation is not None
    assert (
        candidate_by_family["logistic_regression"].evaluation.average_precision
        >= candidate_by_family["dummy_prior"].evaluation.average_precision
    )


def test_train_baseline_from_examples_raises_when_training_data_is_stale(tmp_path) -> None:
    try:
        train_baseline_from_examples(
            sample_training_examples(),
            feature_build_version="sample-v1",
            label_sources=["sample_surveillance"],
            output_dir=tmp_path,
            min_train_weeks=2,
            freshness_reference_date=date(2026, 6, 1),
            freshness_policy=FreshnessPolicy(warn_after_days=7, fail_after_days=21),
        )
    except ValueError as exc:
        assert "freshness" in str(exc).lower()
    else:
        raise AssertionError("Expected stale training data to raise ValueError.")
