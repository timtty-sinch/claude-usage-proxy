"""Export commands (CSV and JSON)."""

import csv
import io
import json
import sys
from pathlib import Path

import typer

from claude_proxy.db.engine import SyncSessionLocal
from claude_proxy.db.repository import export_all

app = typer.Typer(help="Export commands")

_FIELDS = [
    "id",
    "anthropic_request_id",
    "requested_at",
    "completed_at",
    "duration_ms",
    "model",
    "endpoint",
    "is_streaming",
    "stop_reason",
    "system_prompt_preview",
    "first_user_message_preview",
    "http_status",
    "error_type",
    "error_message",
    "input_tokens",
    "output_tokens",
    "cache_read_tokens",
    "cache_creation_tokens",
    "input_cost_usd",
    "output_cost_usd",
    "cache_read_cost_usd",
    "cache_creation_cost_usd",
    "total_cost_usd",
]


@app.command("csv")
def export_csv(
    output: Path | None = typer.Option(None, "--output", "-o", help="Output file (default: stdout)"),
) -> None:
    """Export all requests as CSV."""
    with SyncSessionLocal() as session:
        rows = export_all(session)

    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=_FIELDS, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)

    content = buf.getvalue()

    if output:
        output.write_text(content, encoding="utf-8")
        typer.echo(f"Exported {len(rows)} records to {output}", err=True)
    else:
        sys.stdout.write(content)


@app.command("json")
def export_json(
    output: Path | None = typer.Option(None, "--output", "-o", help="Output file (default: stdout)"),
) -> None:
    """Export all requests as JSON."""
    with SyncSessionLocal() as session:
        rows = export_all(session)

    content = json.dumps(rows, indent=2, default=str)

    if output:
        output.write_text(content, encoding="utf-8")
        typer.echo(f"Exported {len(rows)} records to {output}", err=True)
    else:
        sys.stdout.write(content)
        sys.stdout.write("\n")
