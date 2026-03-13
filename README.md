# Claude Usage Proxy

A local HTTP proxy that intercepts Claude API calls and records token usage, cost, and timing to a local SQLite database. Useful for tracking spend across the team without changes to application code.

## How it works

Point your Anthropic client at the proxy instead of `api.anthropic.com`. The proxy forwards every request upstream transparently and logs usage in the background. No API keys are stored — the proxy just passes through whatever auth header your client sends.

## Setup

Requires Python 3.13+.

```bash
git clone https://github.com/timtty-sinch/claude-usage-proxy
cd claude-usage-proxy
python3.13 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
alembic upgrade head
```

## Running

```bash
claude-proxy serve          # start proxy on http://127.0.0.1:8082
claude-proxy tui            # live dashboard
claude-proxy stats summary  # cost summary table
claude-proxy list requests  # recent requests
claude-proxy export csv     # CSV to stdout
claude-proxy export json    # JSON to stdout
```

## Pointing your client at the proxy

```python
import anthropic

client = anthropic.Anthropic(
    base_url="http://127.0.0.1:8082",
    # api_key is still read from ANTHROPIC_API_KEY as normal
)
```

For Claude Code, set the environment variable before launching:

```bash
ANTHROPIC_BASE_URL=http://127.0.0.1:8082 claude
```

## Configuration

All settings can be overridden via environment variables or a `.env` file:

| Variable | Default | Description |
|---|---|---|
| `CLAUDE_PROXY_HOST` | `127.0.0.1` | Host to bind |
| `CLAUDE_PROXY_PORT` | `8082` | Port to listen on |
| `CLAUDE_PROXY_UPSTREAM_URL` | `https://api.anthropic.com` | Upstream API |
| `CLAUDE_PROXY_DB_PATH` | `claude_proxy.db` | SQLite database path |

## Dashboard

Run `claude-proxy tui` for a live Textual dashboard showing request history, token counts, and cost breakdowns. Refreshes every 2 seconds.
