"""List requests command."""

from datetime import timezone

import typer
from rich.console import Console
from rich.table import Table

from claude_proxy.db.engine import SyncSessionLocal
from claude_proxy.db.repository import list_requests

console = Console()
app = typer.Typer(help="List commands")


@app.command("requests")
def requests_cmd(
    limit: int = typer.Option(20, "--limit", "-n", help="Maximum number of requests to show"),
    model: str | None = typer.Option(None, "--model", "-m", help="Filter by model name"),
) -> None:
    """Show recent API requests."""
    with SyncSessionLocal() as session:
        rows = list_requests(session, limit=limit, model=model)

    if not rows:
        console.print("[yellow]No requests found.[/yellow]")
        raise typer.Exit()

    table = Table(title="Recent Requests", show_lines=True)
    table.add_column("Time (UTC)", style="dim", no_wrap=True)
    table.add_column("Model", style="cyan")
    table.add_column("S", justify="center")
    table.add_column("Complexity", justify="center")
    table.add_column("In", justify="right")
    table.add_column("Out", justify="right")
    table.add_column("Cost (USD)", justify="right", style="green")
    table.add_column("ms", justify="right")
    table.add_column("Status", justify="center")

    for row in rows:
        ts = row["requested_at"]
        if ts and ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        time_str = ts.strftime("%m-%d %H:%M:%S") if ts else "-"
        stream_icon = "~" if row["is_streaming"] else " "
        status_str = str(row["http_status"]) if row["http_status"] else "-"
        if row["error_type"]:
            status_str = f"[red]{status_str}[/red]"

        complexity = row.get("complexity") or "—"
        complexity_styled = {"low": "[green]low[/green]", "med": "[yellow]med[/yellow]", "high": "[red]high[/red]"}.get(complexity, complexity)

        table.add_row(
            time_str,
            row["model"],
            stream_icon,
            complexity_styled,
            f"{row['input_tokens']:,}",
            f"{row['output_tokens']:,}",
            f"${row['total_cost_usd']:.6f}",
            str(row["duration_ms"]) if row["duration_ms"] is not None else "-",
            status_str,
        )

    console.print(table)
