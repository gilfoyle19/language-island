"""Small, side-effect-light diagnostics used by the API and status UI."""

from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path
from typing import Any

import httpx

from language_island.settings import Settings


def _check_writable(path: Path) -> dict[str, Any]:
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".write-probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
    except OSError as exc:
        return {"status": "error", "path": str(path.resolve()), "detail": str(exc)}
    return {"status": "ready", "path": str(path.resolve())}


def _check_sqlite(settings: Settings) -> dict[str, Any]:
    try:
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(settings.database_path) as connection:
            connection.execute("SELECT 1")
    except sqlite3.Error as exc:
        return {"status": "error", "path": str(settings.database_path), "detail": str(exc)}
    return {"status": "ready", "path": str(settings.database_path.resolve())}


def _check_ollama(settings: Settings) -> dict[str, Any]:
    executable = shutil.which("ollama")
    if executable is None:
        return {"status": "unavailable", "detail": "ollama executable was not found on PATH"}

    try:
        response = httpx.get(f"{settings.ollama_base_url}/api/tags", timeout=1.0)
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        return {
            "status": "unavailable",
            "executable": executable,
            "detail": f"Ollama is installed but its service is unavailable: {exc}",
        }

    model_names = {
        model.get("name")
        for model in payload.get("models", [])
        if isinstance(model, dict)
    }
    model_ready = settings.ollama_model in model_names
    return {
        "status": "ready" if model_ready else "model_missing",
        "executable": executable,
        "model": settings.ollama_model,
        "model_ready": model_ready,
    }


def run_diagnostics(settings: Settings) -> dict[str, Any]:
    """Return readiness details without making optional dependencies fatal."""
    settings.prepare_local_directories()
    components = {
        "data_directory": _check_writable(settings.data_dir),
        "model_directory": _check_writable(settings.model_dir),
        "sqlite": _check_sqlite(settings),
        "ollama": _check_ollama(settings),
    }
    required_ready = all(
        components[name]["status"] == "ready"
        for name in ("data_directory", "model_directory", "sqlite")
    )
    return {
        "status": "ready" if required_ready else "error",
        "environment": settings.environment,
        "components": components,
    }
