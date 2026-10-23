"""FastAPI entry point."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException

from language_island import __version__
from language_island.api.schemas import (
    LearnerTurnRequest,
    StartConversationRequest,
    StartConversationResponse,
)
from language_island.curriculum import load_curriculum
from language_island.diagnostics import run_diagnostics
from language_island.settings import Settings, get_settings
from language_island.storage import Database, LearningStore
from language_island.tutor import OllamaTutorModel, TutorEngine, TutorLanguageModel
from language_island.tutor.models import TutorReply


def create_app(
    settings: Settings | None = None,
    tutor_model: TutorLanguageModel | None = None,
) -> FastAPI:
    app_settings = settings or get_settings()
    curriculum = load_curriculum(app_settings.curriculum_dir)
    database = Database(app_settings.database_path)
    store = LearningStore(database)
    model = tutor_model or OllamaTutorModel(
        model=app_settings.ollama_model,
        base_url=app_settings.ollama_base_url,
    )
    tutor = TutorEngine(model=model, curriculum=curriculum, store=store)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app_settings.prepare_local_directories()
        await database.initialize()
        app.state.database = database
        app.state.tutor = tutor
        try:
            yield
        finally:
            await database.dispose()

    app = FastAPI(
        title=app_settings.app_name,
        version=__version__,
        lifespan=lifespan,
    )

    @app.get("/health")
    def health() -> dict[str, object]:
        return run_diagnostics(app_settings)

    @app.get("/api/islands")
    def list_islands() -> list[dict[str, object]]:
        island = curriculum.island
        return [
            {
                "id": island.id,
                "title": island.title,
                "category": island.category,
                "supported_levels": island.supported_levels,
            }
        ]

    @app.get("/api/islands/{island_id}")
    def get_island(island_id: str) -> dict[str, object]:
        if island_id != curriculum.island.id:
            raise HTTPException(status_code=404, detail="Island not found")
        return curriculum.island.model_dump(mode="json")

    @app.post("/api/conversations", response_model=StartConversationResponse)
    async def start_conversation(
        request: StartConversationRequest,
    ) -> StartConversationResponse:
        plan = curriculum.island.levels.get(request.level)
        if plan is None:
            raise HTTPException(status_code=400, detail="Level is not available")
        scenario_id = request.scenario_id or plan.scenarios[0].id
        if scenario_id not in {scenario.id for scenario in plan.scenarios}:
            raise HTTPException(status_code=400, detail="Scenario is not available at this level")
        personality_id = request.personality_id or curriculum.island.default_personality_id
        if personality_id not in curriculum.island.allowed_personality_ids:
            raise HTTPException(status_code=400, detail="Personality is not available")

        learner_id = request.learner_id
        if learner_id is None:
            learner = await store.create_learner(request.display_name)
            learner_id = learner.id
        elif await store.get_learner(learner_id) is None:
            raise HTTPException(status_code=404, detail="Learner not found")

        conversation = await store.start_session(
            learner_id=learner_id,
            island_id=curriculum.island.id,
            level=request.level.value,
            scenario_id=scenario_id,
            personality_id=personality_id,
        )
        try:
            opening = await tutor.opening(conversation.id)
        except Exception as exc:
            raise HTTPException(status_code=503, detail=f"Tutor model unavailable: {exc}") from exc
        return StartConversationResponse(
            learner_id=learner_id,
            session_id=conversation.id,
            island_id=conversation.island_id,
            level=request.level,
            scenario_id=scenario_id,
            personality_id=personality_id,
            opening=opening,
        )

    @app.post("/api/conversations/{session_id}/turns", response_model=TutorReply)
    async def submit_turn(session_id: str, request: LearnerTurnRequest) -> TutorReply:
        try:
            return await tutor.handle_turn(session_id, request.text)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=503, detail=f"Tutor model unavailable: {exc}") from exc

    return app


app = create_app()
