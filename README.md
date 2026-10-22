# Language Island

A local-first German voice tutor built around reusable language islands. The first vertical
slice will teach the Café island from A1 through C1.

## Prerequisites

- Windows 11
- `uv`
- Ollama with `qwen3:8b`

Install the managed Python runtime and synchronize the locked environment:

```powershell
uv python install 3.11
$env:UV_CACHE_DIR = Join-Path (Get-Location) ".uv-cache"
uv sync --locked --all-groups
```

Run the checks:

```powershell
uv run --locked pytest
uv run --locked ruff check .
uv run --locked mypy src
```

Start FastAPI and Streamlit together:

```powershell
.\scripts\start.ps1
```

The API health endpoint is available at `http://127.0.0.1:8000/health` and Streamlit at
`http://127.0.0.1:8501`.

Run local diagnostics without starting either web service:

```powershell
uv run --locked language-island
```
