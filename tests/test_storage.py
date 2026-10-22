from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest

from language_island.curriculum import load_curriculum
from language_island.progress import MetricKind, evaluate_readiness
from language_island.storage import Database, LearningStore


def database_path() -> Path:
    return Path("data") / "test-runtime" / str(uuid4()) / "progress.sqlite3"


@pytest.mark.asyncio
async def test_session_and_bilingual_transcript_are_persisted_in_order() -> None:
    database = Database(database_path())
    await database.initialize()
    store = LearningStore(database)
    try:
        learner = await store.create_learner("Alex")
        conversation = await store.start_session(
            learner_id=learner.id,
            island_id="cafe",
            level="A1",
            scenario_id="a1_counter_order",
            personality_id="patient_barista",
        )
        await store.append_turn(
            session_id=conversation.id,
            speaker="tutor",
            german_text="Guten Morgen! Was möchten Sie?",
            english_translation="Good morning! What would you like?",
        )
        await store.append_turn(
            session_id=conversation.id,
            speaker="learner",
            german_text="Ich möchte einen Kaffee, bitte.",
            english_translation="I would like a coffee, please.",
        )

        transcript = await store.get_transcript(conversation.id)

        assert [turn.sequence for turn in transcript] == [1, 2]
        assert [turn.speaker for turn in transcript] == ["tutor", "learner"]
        assert transcript[1].english_translation == "I would like a coffee, please."
    finally:
        await database.dispose()


@pytest.mark.asyncio
async def test_quantitative_snapshot_tracks_independence_and_learned_words() -> None:
    database = Database(database_path())
    await database.initialize()
    store = LearningStore(database)
    try:
        learner = await store.create_learner()
        conversation = await store.start_session(
            learner_id=learner.id,
            island_id="cafe",
            level="A1",
            scenario_id="a1_counter_order",
            personality_id="patient_barista",
        )
        for successful in (True, True, True):
            await store.record_event(
                session_id=conversation.id,
                kind=MetricKind.VOCABULARY,
                item_id="kaffee",
                successful=successful,
                delayed=True,
            )
        await store.record_event(
            session_id=conversation.id,
            kind=MetricKind.GRAMMAR,
            item_id="accusative_articles",
            successful=True,
        )
        await store.record_event(
            session_id=conversation.id,
            kind=MetricKind.GRAMMAR,
            item_id="accusative_articles",
            successful=False,
            independent=False,
        )
        await store.record_event(
            session_id=conversation.id,
            kind=MetricKind.OBJECTIVE,
            item_id="a1_order",
            successful=True,
        )
        await store.finish_session(conversation.id)

        snapshot = await store.progress_snapshot(
            learner_id=learner.id,
            island_id="cafe",
            level="A1",
            objective_ids={"a1_order", "a1_pay"},
        )

        assert snapshot.completed_sessions == 1
        assert snapshot.distinct_scenarios == 1
        assert snapshot.grammar.opportunities == 1
        assert snapshot.grammar.rate == 1.0
        assert snapshot.learned_vocabulary_ids == ["kaffee"]
        assert snapshot.objective_coverage == 0.5
    finally:
        await database.dispose()


@pytest.mark.asyncio
async def test_readiness_reports_each_failed_quantitative_gate() -> None:
    database = Database(database_path())
    await database.initialize()
    store = LearningStore(database)
    try:
        learner = await store.create_learner()
        snapshot = await store.progress_snapshot(
            learner_id=learner.id,
            island_id="cafe",
            level="A1",
            objective_ids={"a1_order", "a1_pay"},
        )
        rule = load_curriculum(Path("config")).progression.rules["A1"]

        readiness = evaluate_readiness(snapshot, rule)

        assert readiness.ready is False
        assert {gate.metric for gate in readiness.gates if not gate.passed} == {
            "completed_sessions",
            "distinct_scenarios",
            "grammar_opportunities",
            "grammar_accuracy",
            "task_checks",
            "task_success",
            "delayed_vocabulary_checks",
            "delayed_vocabulary_recall",
            "listening_checks",
            "listening_success",
            "transfer_checks",
            "transfer_success",
            "objective_coverage",
        }
    finally:
        await database.dispose()
