from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from language_island.curriculum.loader import (
    CurriculumError,
    load_curriculum,
    parse_yaml_text,
    validate_bundle,
)
from language_island.curriculum.models import VocabularyCatalog

CONFIG_DIR = Path("config")


def test_cafe_curriculum_loads_with_complete_levels() -> None:
    bundle = load_curriculum(CONFIG_DIR)

    assert bundle.island.id == "cafe"
    assert [level.value for level in bundle.island.supported_levels] == [
        "A1",
        "A2",
        "B1",
        "B2",
        "C1",
    ]
    for plan in bundle.island.levels.values():
        assert plan.objectives
        assert plan.vocabulary_ids
        assert plan.grammar_ids
        assert plan.scenarios
        assert all(scenario.success_criteria for scenario in plan.scenarios)


def test_feedback_language_and_required_retry_match_product_rules() -> None:
    policy = load_curriculum(CONFIG_DIR).island.feedback

    assert policy.require_successful_retry is True
    assert policy.timing == "natural_pause"
    assert policy.explanation_language["A1"] == "en"
    assert policy.explanation_language["A2"] == "en"
    assert policy.explanation_language["B1"] == "de"
    assert policy.explanation_language["C1"] == "de"


def test_malformed_yaml_is_rejected() -> None:
    with pytest.raises(CurriculumError, match="Invalid YAML"):
        parse_yaml_text("levels: [A1, A2", "broken.yaml")


def test_duplicate_vocabulary_ids_are_rejected() -> None:
    entry = {
        "id": "kaffee",
        "lemma": "Kaffee",
        "english": "coffee",
        "part_of_speech": "noun",
        "article": "der",
        "plural": "die Kaffees",
        "levels": ["A1"],
    }
    with pytest.raises(ValidationError, match="duplicate vocabulary ids"):
        VocabularyCatalog.model_validate({"entries": [entry, entry]})


def test_missing_cross_file_reference_is_rejected() -> None:
    bundle = load_curriculum(CONFIG_DIR).model_copy(deep=True)
    bundle.island.levels["A1"].vocabulary_ids.append("does_not_exist")

    with pytest.raises(CurriculumError, match="unknown vocabulary reference"):
        validate_bundle(bundle)
