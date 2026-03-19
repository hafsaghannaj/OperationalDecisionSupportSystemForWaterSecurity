from outbreaks.cag.engine import CAGEngine


def test_engine_answers_from_general_cache() -> None:
    answer = CAGEngine().ask("What actions are recommended at elevated risk?")

    assert answer.cache_type == "general"
    assert answer.used_region is None
    assert "chlorination checks" in answer.answer.lower()


def test_engine_answers_from_region_cache() -> None:
    answer = CAGEngine().ask("How should we plan river delta operations?", "example_region")

    assert answer.cache_type == "region"
    assert answer.used_region == "example_region"
    assert "boat-access teams" in answer.answer.lower()
