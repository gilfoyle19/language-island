from __future__ import annotations

from collections import deque
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from language_island.api.app import create_app
from language_island.curriculum import load_curriculum
from language_island.settings import Settings
from language_island.storage import Database, LearningStore
from language_island.tutor import TutorEngine
from language_island.tutor.models import (
    SkillEvidence,
    TutorAssessment,
    TutorModelInput,
)


class FakeTutorModel:
    def __init__(self, responses: list[TutorAssessment]) -> None:
        self.responses = deque(responses)
        self.requests: list[TutorModelInput] = []

    async def generate(self, request: TutorModelInput) -> TutorAssessment:
        self.requests.append(request)
        return self.responses.popleft()


def database_path() -> Path:
    return Path("data") / "test-runtime" / str(uuid4()) / "tutor.sqlite3"


def opening_assessment() -> TutorAssessment:
    return TutorAssessment(
        is_correct=True,
        tutor_german="Guten Tag! Was möchten Sie bestellen?",
        tutor_english="Good afternoon! What would you like to order?",
    )


@pytest.mark.asyncio
async def test_correction_blocks_conversation_until_exact_retry() -> None:
    model = FakeTutorModel(
        [
            opening_assessment(),
            TutorAssessment(
                learner_english="I would like a coffee.",
                is_correct=False,
                corrected_german="Ich möchte einen Kaffee.",
                corrected_english="I would like a coffee.",
                correction_explanation="Use einen because Kaffee is masculine and accusative.",
                retry_text="Ich möchte einen Kaffee.",
                grammar_evidence=[
                    SkillEvidence(item_id="accusative_articles", successful=False)
                ],
            ),
            TutorAssessment(
                learner_english="I would like a coffee.",
                is_correct=True,
                tutor_german="Sehr gut. Möchten Sie auch einen Kuchen?",
                tutor_english="Very good. Would you also like a cake?",
                grammar_evidence=[
                    SkillEvidence(item_id="accusative_articles", successful=True)
                ],
            ),
        ]
    )
    database = Database(database_path())
    await database.initialize()
    store = LearningStore(database)
    engine = TutorEngine(
        model=model,
        curriculum=load_curriculum(Path("config")),
        store=store,
    )
    try:
        learner = await store.create_learner()
        conversation = await store.start_session(
            learner_id=learner.id,
            island_id="cafe",
            level="A1",
            scenario_id="a1_counter_order",
            personality_id="patient_barista",
        )
        await engine.opening(conversation.id)

        correction = await engine.handle_turn(conversation.id, "Ich möchte ein Kaffee.")
        repeated_correction = await engine.handle_turn(conversation.id, "einen Kaffee")
        continuation = await engine.handle_turn(
            conversation.id, "Ich möchte einen Kaffee."
        )

        assert correction.status == "retry"
        assert correction.required_retry == "Ich möchte einen Kaffee."
        assert repeated_correction.status == "retry"
        assert len(model.requests) == 3
        assert continuation.status == "continue"
        assert continuation.tutor_german == "Sehr gut. Möchten Sie auch einen Kuchen?"
        assert await store.get_tutor_state(conversation.id) == {}
        assert model.requests[1].explanation_language == "en"

        snapshot = await store.progress_snapshot(
            learner_id=learner.id,
            island_id="cafe",
            level="A1",
            objective_ids=set(),
        )
        assert snapshot.grammar.opportunities == 1
        assert snapshot.grammar.successes == 0
    finally:
        await database.dispose()


@pytest.mark.asyncio
async def test_b1_uses_german_explanations_and_selected_personality() -> None:
    model = FakeTutorModel(
        [
            opening_assessment(),
            TutorAssessment(
                learner_english="The soup is unfortunately cold.",
                is_correct=True,
                tutor_german="Das tut mir leid. Was kann ich für Sie tun?",
                tutor_english="I am sorry. What can I do for you?",
            ),
        ]
    )
    database = Database(database_path())
    await database.initialize()
    store = LearningStore(database)
    engine = TutorEngine(
        model=model,
        curriculum=load_curriculum(Path("config")),
        store=store,
    )
    try:
        learner = await store.create_learner()
        conversation = await store.start_session(
            learner_id=learner.id,
            island_id="cafe",
            level="B1",
            scenario_id="b1_cold_meal",
            personality_id="efficient_waiter",
        )
        await engine.opening(conversation.id)
        await engine.handle_turn(conversation.id, "Die Suppe ist leider kalt.")

        request = model.requests[-1]
        assert request.explanation_language == "de"
        assert request.personality_name == "Thomas, the efficient waiter"
        assert request.conversational_register == "Sie"
        assert "subordinate_contrast" in request.grammar
    finally:
        await database.dispose()


def test_text_conversation_api_starts_and_requests_retry() -> None:
    model = FakeTutorModel(
        [
            opening_assessment(),
            TutorAssessment(
                learner_english="I would like a coffee.",
                is_correct=False,
                corrected_german="Ich möchte einen Kaffee.",
                corrected_english="I would like a coffee.",
                correction_explanation="Use the masculine accusative article einen.",
                retry_text="Ich möchte einen Kaffee.",
            ),
        ]
    )
    root = database_path().parent
    settings = Settings(
        data_dir=root,
        model_dir=root / "models",
        ollama_base_url="http://127.0.0.1:1",
    )

    with TestClient(create_app(settings, tutor_model=model)) as client:
        started = client.post("/api/conversations", json={"level": "A1"})
        assert started.status_code == 200
        session_id = started.json()["session_id"]

        turn = client.post(
            f"/api/conversations/{session_id}/turns",
            json={"text": "Ich möchte ein Kaffee."},
        )

    assert turn.status_code == 200
    assert turn.json()["status"] == "retry"
    assert turn.json()["required_retry"] == "Ich möchte einen Kaffee."
