# Claude Usage Proxy — Development Instructions

## Branching (PRIMARY MANDATE)

**All new features must be developed on a dedicated branch.**

Before starting any feature work:

```bash
git checkout -b feature-<short-description>
# e.g. git checkout -b feature-web-ui
#      git checkout -b feature-cost-alerts
#      git checkout -b feature-request-replay
```

Never commit new features directly to `main`.

## Setup

```bash
source .venv/bin/activate
pip install -e ".[dev]"
alembic upgrade head
```

## Running

```bash
claude-proxy serve          # proxy on http://127.0.0.1:8082
claude-proxy tui            # live Textual dashboard
claude-proxy stats summary  # cost summary table
claude-proxy list requests  # recent requests
claude-proxy export csv     # CSV export to stdout
claude-proxy export json    # JSON export to stdout
```

## Stack

| Concern | Library |
|---|---|
| Proxy server | FastAPI + uvicorn |
| Async HTTP client | httpx |
| ORM | SQLAlchemy 2.0 async |
| Migrations | Alembic |
| CLI | Typer + Rich |
| TUI | Textual |
| Config | pydantic-settings (`CLAUDE_PROXY_` prefix) |
| DB | SQLite via aiosqlite (async) / sqlite3 (sync CLI) |

## Key Files

- `src/claude_proxy/config.py` — settings
- `src/claude_proxy/pricing.py` — cost calculation
- `src/claude_proxy/db/models.py` — ORM models (`ApiRequest`, `ApiUsage`)
- `src/claude_proxy/db/engine.py` — async + sync engines
- `src/claude_proxy/db/repository.py` — sync query helpers for CLI/TUI
- `src/claude_proxy/proxy/routes.py` — wildcard proxy route
- `src/claude_proxy/proxy/streaming.py` — SSE capture (`StreamCapture`)
- `src/claude_proxy/cli/main.py` — CLI entry point
- `src/claude_proxy/cli/tui/dashboard.py` — Textual dashboard

## Database Migrations

After changing models, generate and apply a migration:

```bash
alembic revision --autogenerate -m "describe change"
alembic upgrade head
```

## Config

Environment variables (or `.env` file):

```
CLAUDE_PROXY_HOST=127.0.0.1
CLAUDE_PROXY_PORT=8082
CLAUDE_PROXY_UPSTREAM_URL=https://api.anthropic.com
CLAUDE_PROXY_DB_PATH=claude_proxy.db
```
