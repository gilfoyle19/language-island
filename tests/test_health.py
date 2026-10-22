from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

from language_island.api.app import create_app
from language_island.settings import Settings


def test_health_endpoint_prepares_local_storage() -> None:
    test_root = Path("data") / "test-runtime" / str(uuid4())
    settings = Settings(
        data_dir=test_root / "data",
        model_dir=test_root / "models",
        ollama_base_url="http://127.0.0.1:1",
    )

    with TestClient(create_app(settings)) as client:
        response = client.get("/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ready"
    assert payload["components"]["sqlite"]["status"] == "ready"
    assert payload["components"]["ollama"]["status"] in {
        "ready",
        "model_missing",
        "unavailable",
    }
    assert settings.data_dir.is_dir()
    assert settings.model_dir.is_dir()
    assert settings.database_path.is_file()


def test_cafe_island_endpoint() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/api/islands/cafe")

    assert response.status_code == 200
    assert response.json()["supported_levels"] == ["A1", "A2", "B1", "B2", "C1"]


def test_unknown_island_returns_404() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/api/islands/unknown")

    assert response.status_code == 404
