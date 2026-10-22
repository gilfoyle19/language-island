"""Quantitative progress snapshots and level-readiness evaluation."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from language_island.curriculum.models import ProgressionRule


class MetricKind(StrEnum):
    VOCABULARY = "vocabulary"
    GRAMMAR = "grammar"
    TASK = "task"
    LISTENING = "listening"
    TRANSFER = "transfer"
    OBJECTIVE = "objective"


class MetricSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    opportunities: int = 0
    successes: int = 0
    rate: float = Field(ge=0, le=1)

    @classmethod
    def from_results(cls, results: list[bool]) -> MetricSummary:
        successes = sum(results)
        return cls(
            opportunities=len(results),
            successes=successes,
            rate=successes / len(results) if results else 0.0,
        )


class VocabularyItemProgress(BaseModel):
    item_id: str
    delayed_checks: int
    delayed_successes: int
    recall_rate: float = Field(ge=0, le=1)
    mastered: bool


class ProgressSnapshot(BaseModel):
    learner_id: str
    island_id: str
    level: str
    completed_sessions: int
    distinct_scenarios: int
    grammar: MetricSummary
    tasks: MetricSummary
    delayed_vocabulary: MetricSummary
    listening: MetricSummary
    transfer: MetricSummary
    objective_coverage: float = Field(ge=0, le=1)
    vocabulary: list[VocabularyItemProgress]

    @property
    def learned_vocabulary_ids(self) -> list[str]:
        return [item.item_id for item in self.vocabulary if item.mastered]


class ProgressGate(BaseModel):
    metric: str
    actual: float
    required: float
    passed: bool


class ReadinessResult(BaseModel):
    ready: bool
    gates: list[ProgressGate]


def evaluate_readiness(snapshot: ProgressSnapshot, rule: ProgressionRule) -> ReadinessResult:
    checks = [
        ("completed_sessions", snapshot.completed_sessions, rule.min_sessions),
        ("distinct_scenarios", snapshot.distinct_scenarios, rule.min_distinct_scenarios),
        ("grammar_opportunities", snapshot.grammar.opportunities, rule.min_grammar_opportunities),
        ("grammar_accuracy", snapshot.grammar.rate, rule.min_independent_grammar_accuracy),
        ("task_checks", snapshot.tasks.opportunities, rule.min_task_checks),
        ("task_success", snapshot.tasks.rate, rule.min_task_success),
        (
            "delayed_vocabulary_checks",
            snapshot.delayed_vocabulary.opportunities,
            rule.min_delayed_vocabulary_checks,
        ),
        (
            "delayed_vocabulary_recall",
            snapshot.delayed_vocabulary.rate,
            rule.min_delayed_vocabulary_recall,
        ),
        ("listening_checks", snapshot.listening.opportunities, rule.min_listening_checks),
        ("listening_success", snapshot.listening.rate, rule.min_listening_success),
        ("transfer_checks", snapshot.transfer.opportunities, rule.min_transfer_checks),
        ("transfer_success", snapshot.transfer.rate, rule.min_transfer_success),
        ("objective_coverage", snapshot.objective_coverage, rule.required_objective_coverage),
    ]
    gates = [
        ProgressGate(
            metric=name,
            actual=float(actual),
            required=float(required),
            passed=actual >= required,
        )
        for name, actual, required in checks
    ]
    return ReadinessResult(ready=all(gate.passed for gate in gates), gates=gates)
