"""FastAPI entry point."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException

from language_island import __version__
from language_island.curriculum import load_curriculum
from language_island.diagnostics import run_diagnostics
from language_island.settings import Settings, get_settings
from language_island.storage import Database


def create_app(settings: Settings | None = None) -> FastAPI:
    app_settings = settings or get_settings()
    curriculum = load_curriculum(app_settings.curriculum_dir)
    database = Database(app_settings.database_path)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app_settings.prepare_local_directories()
        await database.initialize()
        app.state.database = database
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

    return app


app = create_app()
