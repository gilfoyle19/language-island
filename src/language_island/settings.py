"""Application configuration and local storage paths."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuration loaded from environment variables prefixed with ``LI_``."""

    model_config = SettingsConfigDict(
        env_prefix="LI_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Language Island"
    environment: str = "development"
    api_host: str = "127.0.0.1"
    api_port: int = 8000
    streamlit_port: int = 8501
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen3:8b"
    data_dir: Path = Field(default=Path("data"))
    model_dir: Path = Field(default=Path("models"))

    @property
    def database_path(self) -> Path:
        return self.data_dir / "language_island.sqlite3"

    @property
    def api_url(self) -> str:
        return f"http://{self.api_host}:{self.api_port}"

    def prepare_local_directories(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.model_dir.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    return Settings()
