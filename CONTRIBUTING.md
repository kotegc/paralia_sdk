# Contributing

## Setup

```bash
python -m venv .venv
source .venv/bin/activate   # or .venv\Scripts\activate on Windows
pip install -e ".[dev]"
```

## Running tests

```bash
pytest tests/ -v
```

CI runs this same command on every push/PR (`.github/workflows/test.yml`), against Python 3.10–3.12.

## Adding a new per-service client

Keep it a thin subclass of `paralia_sdk.http.BaseClient` — auth, request/response shaping, error handling only. No side effects (file I/O, etc.) baked into the client; that belongs in whatever application calls it. See `paradigm_client.py`/`parable_client.py` as the two existing examples.

## Known gaps

See `TESTING.md` for what's currently untested and why it matters.
