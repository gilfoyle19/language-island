"""Async SQLAlchemy database lifecycle."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlalchemy import URL, event
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from language_island.storage.models import Base


class Database:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        url = URL.create("sqlite+aiosqlite", database=str(path.resolve()))
        self.engine: AsyncEngine = create_async_engine(url)
        event.listen(self.engine.sync_engine, "connect", _enable_sqlite_foreign_keys)
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)

    async def initialize(self) -> None:
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    def session(self) -> AsyncSession:
        return self.sessions()

    async def dispose(self) -> None:
        await self.engine.dispose()


def _enable_sqlite_foreign_keys(dbapi_connection: Any, _: Any) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()
