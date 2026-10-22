"""Load and cross-validate YAML curriculum files."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from language_island.curriculum.models import (
    CurriculumBundle,
    GrammarCatalog,
    IslandConfig,
    PersonalityCatalog,
    ProgressionConfig,
    VocabularyCatalog,
)


class CurriculumError(ValueError):
    """A curriculum file is malformed or inconsistent with another file."""


def parse_yaml_text(text: str, source: str = "<memory>") -> dict[str, Any]:
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise CurriculumError(f"Invalid YAML in {source}: {exc}") from exc
    if not isinstance(data, dict):
        raise CurriculumError(f"Expected a YAML mapping in {source}")
    return data


def _read_yaml(path: Path) -> dict[str, Any]:
    try:
        return parse_yaml_text(path.read_text(encoding="utf-8"), str(path))
    except OSError as exc:
        raise CurriculumError(f"Cannot read curriculum file {path}: {exc}") from exc


def load_curriculum(config_dir: Path, island_id: str = "cafe") -> CurriculumBundle:
    try:
        bundle = CurriculumBundle(
            island=IslandConfig.model_validate(
                _read_yaml(config_dir / "islands" / f"{island_id}.yaml")
            ),
            vocabulary=VocabularyCatalog.model_validate(
                _read_yaml(config_dir / "vocabulary" / "de.yaml")
            ),
            grammar=GrammarCatalog.model_validate(
                _read_yaml(config_dir / "grammar" / "de.yaml")
            ),
            personalities=PersonalityCatalog.model_validate(
                _read_yaml(config_dir / "personalities.yaml")
            ),
            progression=ProgressionConfig.model_validate(
                _read_yaml(config_dir / "progression.yaml")
            ),
        )
    except ValidationError as exc:
        raise CurriculumError(f"Curriculum schema validation failed: {exc}") from exc
    validate_bundle(bundle)
    return bundle


def validate_bundle(bundle: CurriculumBundle) -> None:
    issues: list[str] = []
    vocabulary = bundle.vocabulary.by_id()
    grammar = bundle.grammar.by_id()
    personalities = bundle.personalities.by_id()
    island = bundle.island

    if island.default_personality_id not in island.allowed_personality_ids:
        issues.append("default personality is not allowed by the island")
    for personality_id in island.allowed_personality_ids:
        if personality_id not in personalities:
            issues.append(f"unknown personality reference: {personality_id}")

    for level, plan in island.levels.items():
        if level not in island.feedback.explanation_language:
            issues.append(f"missing feedback language for {level}")
        if level not in bundle.progression.rules:
            issues.append(f"missing progression rule for {level}")
        for vocabulary_id in plan.vocabulary_ids:
            entry = vocabulary.get(vocabulary_id)
            if entry is None:
                issues.append(f"{level}: unknown vocabulary reference: {vocabulary_id}")
            elif level not in entry.levels:
                issues.append(f"{level}: vocabulary {vocabulary_id} is not tagged for this level")
        for grammar_id in plan.grammar_ids:
            skill = grammar.get(grammar_id)
            if skill is None:
                issues.append(f"{level}: unknown grammar reference: {grammar_id}")
            elif level not in skill.levels:
                issues.append(f"{level}: grammar {grammar_id} is not tagged for this level")

    for skill in bundle.grammar.skills:
        for prerequisite in skill.prerequisites:
            if prerequisite not in grammar:
                issues.append(f"{skill.id}: unknown prerequisite: {prerequisite}")
            elif prerequisite == skill.id:
                issues.append(f"{skill.id}: cannot require itself")

    for connection in island.connections:
        for vocabulary_id in connection.shared_vocabulary_ids:
            if vocabulary_id not in vocabulary:
                issues.append(
                    f"connection {connection.target_island_id}: unknown vocabulary {vocabulary_id}"
                )
        for grammar_id in connection.shared_grammar_ids:
            if grammar_id not in grammar:
                issues.append(
                    f"connection {connection.target_island_id}: unknown grammar {grammar_id}"
                )

    if issues:
        raise CurriculumError("Curriculum references are invalid:\n- " + "\n- ".join(issues))
