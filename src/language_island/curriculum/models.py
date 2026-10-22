"""Pydantic models for island, vocabulary, grammar, and progression data."""

from __future__ import annotations

from collections.abc import Iterable
from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CEFRLevel(StrEnum):
    A1 = "A1"
    A2 = "A2"
    B1 = "B1"
    B2 = "B2"
    C1 = "C1"
    C2 = "C2"


class PartOfSpeech(StrEnum):
    NOUN = "noun"
    VERB = "verb"
    ADJECTIVE = "adjective"
    ADVERB = "adverb"
    PREPOSITION = "preposition"
    PHRASE = "phrase"


class VocabularyEntry(StrictModel):
    id: str
    lemma: str
    english: str
    part_of_speech: PartOfSpeech
    levels: set[CEFRLevel]
    article: str | None = None
    plural: str | None = None
    principal_parts: list[str] = Field(default_factory=list)
    chunks: list[str] = Field(default_factory=list)
    usage_note: str | None = None

    @model_validator(mode="after")
    def require_word_metadata(self) -> Self:
        if self.part_of_speech is PartOfSpeech.NOUN and self.article is None:
            raise ValueError(f"noun {self.id!r} must define an article")
        if self.part_of_speech is PartOfSpeech.VERB and not self.principal_parts:
            raise ValueError(f"verb {self.id!r} must define principal_parts")
        return self


class VocabularyCatalog(StrictModel):
    schema_version: int = 1
    entries: list[VocabularyEntry]

    @model_validator(mode="after")
    def reject_duplicate_ids(self) -> Self:
        _require_unique((entry.id for entry in self.entries), "vocabulary")
        return self

    def by_id(self) -> dict[str, VocabularyEntry]:
        return {entry.id: entry for entry in self.entries}


class GrammarSkill(StrictModel):
    id: str
    title: str
    description: str
    levels: set[CEFRLevel]
    prerequisites: list[str] = Field(default_factory=list)
    examples: list[str] = Field(min_length=1)


class GrammarCatalog(StrictModel):
    schema_version: int = 1
    skills: list[GrammarSkill]

    @model_validator(mode="after")
    def reject_duplicate_ids(self) -> Self:
        _require_unique((skill.id for skill in self.skills), "grammar")
        return self

    def by_id(self) -> dict[str, GrammarSkill]:
        return {skill.id: skill for skill in self.skills}


class LearningObjective(StrictModel):
    id: str
    description: str
    evidence: str
    minimum_opportunities: int = Field(ge=1)


class Scenario(StrictModel):
    id: str
    title: str
    learner_role: str
    partner_role: str
    situation: str
    success_criteria: list[str] = Field(min_length=1)


class LevelPlan(StrictModel):
    objectives: list[LearningObjective] = Field(min_length=1)
    vocabulary_ids: list[str] = Field(min_length=1)
    grammar_ids: list[str] = Field(min_length=1)
    scenarios: list[Scenario] = Field(min_length=1)


class FeedbackPolicy(StrictModel):
    timing: str
    require_successful_retry: bool
    explanation_language: dict[CEFRLevel, str]
    uncertain_transcription: str


class IslandConnection(StrictModel):
    target_island_id: str
    shared_vocabulary_ids: list[str] = Field(default_factory=list)
    shared_grammar_ids: list[str] = Field(default_factory=list)
    transfer_scenario: str
    planned: bool = True


class IslandConfig(StrictModel):
    schema_version: int = 1
    id: str
    title: str
    category: str
    description: str
    supported_levels: list[CEFRLevel]
    default_personality_id: str
    allowed_personality_ids: list[str] = Field(min_length=1)
    feedback: FeedbackPolicy
    levels: dict[CEFRLevel, LevelPlan]
    connections: list[IslandConnection] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_level_shape(self) -> Self:
        if len(self.supported_levels) != len(set(self.supported_levels)):
            raise ValueError("supported_levels contains duplicates")
        if set(self.supported_levels) != set(self.levels):
            raise ValueError("supported_levels must match configured levels")
        _require_unique(
            (
                objective.id
                for plan in self.levels.values()
                for objective in plan.objectives
            ),
            "objective",
        )
        _require_unique(
            (
                scenario.id
                for plan in self.levels.values()
                for scenario in plan.scenarios
            ),
            "scenario",
        )
        return self


class Personality(StrictModel):
    id: str
    display_name: str
    gender_presentation: str
    tone: str
    speaking_rate: float = Field(gt=0.5, le=1.5)
    conversational_register: str
    german_voice: str
    english_voice: str
    role_prompt: str
    behaviours: list[str] = Field(min_length=1)


class PersonalityCatalog(StrictModel):
    schema_version: int = 1
    personalities: list[Personality]

    @model_validator(mode="after")
    def reject_duplicate_ids(self) -> Self:
        _require_unique((item.id for item in self.personalities), "personality")
        return self

    def by_id(self) -> dict[str, Personality]:
        return {item.id: item for item in self.personalities}


class ProgressionRule(StrictModel):
    min_sessions: int = Field(ge=1)
    min_distinct_scenarios: int = Field(ge=1)
    min_independent_grammar_accuracy: float = Field(ge=0, le=1)
    min_grammar_opportunities: int = Field(ge=1)
    min_task_success: float = Field(ge=0, le=1)
    min_task_checks: int = Field(ge=1)
    min_delayed_vocabulary_recall: float = Field(ge=0, le=1)
    min_delayed_vocabulary_checks: int = Field(ge=1)
    min_listening_success: float = Field(ge=0, le=1)
    min_listening_checks: int = Field(ge=1)
    min_transfer_success: float = Field(ge=0, le=1)
    min_transfer_checks: int = Field(ge=1)
    required_objective_coverage: float = Field(ge=0, le=1)


class ProgressionConfig(StrictModel):
    schema_version: int = 1
    rules: dict[CEFRLevel, ProgressionRule]


class CurriculumBundle(StrictModel):
    island: IslandConfig
    vocabulary: VocabularyCatalog
    grammar: GrammarCatalog
    personalities: PersonalityCatalog
    progression: ProgressionConfig


def _require_unique(values: Iterable[str], label: str) -> None:
    items = list(values)
    duplicates = sorted({item for item in items if items.count(item) > 1})
    if duplicates:
        raise ValueError(f"duplicate {label} ids: {', '.join(duplicates)}")
