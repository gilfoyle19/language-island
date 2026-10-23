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

The validated Café curriculum lives under `config/`. It contains the A1-C1 level plans,
German vocabulary and grammar catalogs, tutor personalities, feedback rules, and quantitative
progression gates. The API exposes the island at `http://127.0.0.1:8000/api/islands/cafe`.
Invalid YAML, duplicate IDs, or broken cross-file references stop the API at startup.

Learning state is stored locally in `data/language_island.sqlite3`. The storage layer records
ordered bilingual transcript turns and atomic learning evidence for vocabulary, grammar, tasks,
listening, transfer, and level objectives. Readiness is calculated against every quantitative
gate in `config/progression.yaml`; a word counts as learned after at least three delayed checks
with 80% recall.

## Text conversation API

Commit 4 adds the Ollama and LangGraph conversation loop. Start an A1 Café conversation with:

```powershell
$conversation = Invoke-RestMethod `
  -Method Post `
  -Uri http://127.0.0.1:8000/api/conversations `
  -ContentType application/json `
  -Body '{"level":"A1","personality_id":"patient_barista"}'
```

Submit a learner turn with:

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:8000/api/conversations/$($conversation.session_id)/turns" `
  -ContentType application/json `
  -Body '{"text":"Ich möchte ein Kaffee."}'
```

An incorrect turn returns `status: retry` and `required_retry`. The graph will repeat the
correction until that German text is supplied; only then does the tutor continue the scenario.

Run local diagnostics without starting either web service:

```powershell
uv run --locked language-island
```
