"""Language Island application package."""

from __future__ import annotations

import json

from language_island.diagnostics import run_diagnostics
from language_island.settings import get_settings

__version__ = "0.1.0"


def main() -> None:
    """Print local dependency and storage diagnostics."""
    settings = get_settings()
    print(json.dumps(run_diagnostics(settings), indent=2))
