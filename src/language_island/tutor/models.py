"""Typed boundaries between the conversation graph and language model."""

from __future__ import annotations

from typing import Literal, Protocol, Self, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DialogueLine(StrictModel):
    speaker: str
    german: str
    english: str | None = None


class SkillEvidence(StrictModel):
    item_id: str
    successful: bool
    independent: bool = True


TutorMode: TypeAlias = Literal["opening", "assess", "continue_after_retry"]


class TutorModelInput(StrictModel):
    mode: TutorMode
    level: str
    scenario_title: str
    scenario_situation: str
    success_criteria: list[str]
    personality_name: str
    personality_prompt: str
    personality_tone: str
    conversational_register: str
    explanation_language: Literal["en", "de"]
    vocabulary: dict[str, str]
    grammar: dict[str, str]
    history: list[DialogueLine]
    learner_text: str = ""


class TutorAssessment(StrictModel):
    learner_english: str = ""
    is_correct: bool
    corrected_german: str | None = None
    corrected_english: str | None = None
    correction_explanation: str | None = None
    retry_text: str | None = None
    tutor_german: str | None = None
    tutor_english: str | None = None
    vocabulary_evidence: list[SkillEvidence] = Field(default_factory=list)
    grammar_evidence: list[SkillEvidence] = Field(default_factory=list)

    @model_validator(mode="after")
    def require_output_for_decision(self) -> Self:
        if self.is_correct and (not self.tutor_german or not self.tutor_english):
            raise ValueError("correct turns require a bilingual tutor response")
        if not self.is_correct and not all(
            (
                self.corrected_german,
                self.corrected_english,
                self.correction_explanation,
                self.retry_text,
            )
        ):
            raise ValueError("incorrect turns require correction and retry fields")
        return self


class TutorEvaluation(StrictModel):
    """Flat schema used for Ollama's guided learner-turn evaluation."""

    learner_english: str
    is_correct: bool
    corrected_german: str = Field(
        description="Corrected learner utterance when incorrect; empty string when correct"
    )
    corrected_english: str = Field(
        description="English translation of the correction; empty string when correct"
    )
    correction_explanation: str = Field(
        description="Concise correction explanation; empty string when correct"
    )
    retry_text: str = Field(
        description="Exact German repair to repeat; empty string when correct"
    )
    tutor_german: str = Field(
        description="Next in-role tutor turn when correct; empty string when incorrect"
    )
    tutor_english: str = Field(
        description="English translation of tutor turn; empty string when incorrect"
    )
    vocabulary_evidence: list[SkillEvidence] = Field(default_factory=list)
    grammar_evidence: list[SkillEvidence] = Field(default_factory=list)

    def to_assessment(self) -> TutorAssessment:
        return TutorAssessment(
            learner_english=self.learner_english,
            is_correct=self.is_correct,
            corrected_german=self.corrected_german or None,
            corrected_english=self.corrected_english or None,
            correction_explanation=self.correction_explanation or None,
            retry_text=self.retry_text or None,
            tutor_german=self.tutor_german or None,
            tutor_english=self.tutor_english or None,
            vocabulary_evidence=self.vocabulary_evidence,
            grammar_evidence=self.grammar_evidence,
        )


class TutorUtterance(StrictModel):
    """Guided schema for openings and post-repair continuations."""

    learner_english: str = Field(
        description="Learner utterance in English, or empty string for an opening"
    )
    tutor_german: str
    tutor_english: str
    vocabulary_evidence: list[SkillEvidence] = Field(default_factory=list)
    grammar_evidence: list[SkillEvidence] = Field(default_factory=list)

    def to_assessment(self) -> TutorAssessment:
        return TutorAssessment(
            learner_english=self.learner_english,
            is_correct=True,
            tutor_german=self.tutor_german,
            tutor_english=self.tutor_english,
            vocabulary_evidence=self.vocabulary_evidence,
            grammar_evidence=self.grammar_evidence,
        )


class PendingCorrection(StrictModel):
    corrected_german: str
    corrected_english: str
    explanation: str
    retry_text: str


class TutorReply(StrictModel):
    status: Literal["continue", "retry"]
    learner_english: str | None = None
    tutor_german: str | None = None
    tutor_english: str | None = None
    corrected_german: str | None = None
    corrected_english: str | None = None
    correction_explanation: str | None = None
    required_retry: str | None = None
    vocabulary_evidence: list[SkillEvidence] = Field(default_factory=list)
    grammar_evidence: list[SkillEvidence] = Field(default_factory=list)


class TutorLanguageModel(Protocol):
    async def generate(self, request: TutorModelInput) -> TutorAssessment: ...
