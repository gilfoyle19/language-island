from pathlib import Path
from uuid import uuid4

from language_island.settings import Settings


def test_settings_build_expected_paths() -> None:
    test_root = Path("data") / "test-runtime" / str(uuid4())
    settings = Settings(data_dir=test_root / "state", model_dir=test_root / "models")

    settings.prepare_local_directories()

    assert settings.database_path == test_root / "state" / "language_island.sqlite3"
    assert settings.data_dir.is_dir()
    assert settings.model_dir.is_dir()
