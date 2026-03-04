"""Stats summary command."""

import typer
from rich.console import Console
from rich.table import Table

from claude_proxy.db.engine import SyncSessionLocal
from claude_proxy.db.repository import stats_summary

console = Console()
app = typer.Typer(help="Statistics commands")


@app.command("summary")
def summary(
    days: int = typer.Option(7, "--days", "-d", help="Number of days to include"),
) -> None:
    """Show token and cost summary grouped by model."""
    with SyncSessionLocal() as session:
        rows = stats_summary(session, days=days)

    if not rows:
        console.print(f"[yellow]No data found for the last {days} day(s).[/yellow]")
        raise typer.Exit()

    table = Table(title=f"Usage Summary — Last {days} Day(s)", show_lines=True)
    table.add_column("Model", style="cyan", no_wrap=True)
    table.add_column("Requests", justify="right")
    table.add_column("Input Tokens", justify="right")
    table.add_column("Output Tokens", justify="right")
    table.add_column("Cache Read", justify="right")
    table.add_column("Cache Create", justify="right")
    table.add_column("Total Cost (USD)", justify="right", style="green")

    total_requests = 0
    total_cost = 0.0

    for row in rows:
        table.add_row(
            row["model"],
            str(row["request_count"]),
            f"{row['total_input_tokens']:,}",
            f"{row['total_output_tokens']:,}",
            f"{row['total_cache_read_tokens']:,}",
            f"{row['total_cache_creation_tokens']:,}",
            f"${row['total_cost_usd']:.6f}",
        )
        total_requests += row["request_count"]
        total_cost += row["total_cost_usd"]

    table.add_section()
    table.add_row(
        "[bold]TOTAL[/bold]",
        f"[bold]{total_requests}[/bold]",
        "",
        "",
        "",
        "",
        f"[bold]${total_cost:.6f}[/bold]",
    )

    console.print(table)
