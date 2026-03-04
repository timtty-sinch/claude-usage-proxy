"""Typer root CLI: serve, tui, stats, list, export sub-commands."""

import typer

from claude_proxy.cli.commands import export, list_cmd, stats

app = typer.Typer(
    name="claude-proxy",
    help="Claude API usage proxy — track tokens and costs locally.",
    no_args_is_help=True,
)

# Sub-command groups
app.add_typer(stats.app, name="stats")
app.add_typer(list_cmd.app, name="list")
app.add_typer(export.app, name="export")


@app.command()
def serve(
    host: str = typer.Option(None, "--host", help="Bind host (overrides CLAUDE_PROXY_HOST)"),
    port: int = typer.Option(None, "--port", "-p", help="Bind port (overrides CLAUDE_PROXY_PORT)"),
) -> None:
    """Start the proxy server."""
    import uvicorn

    from claude_proxy.config import settings
    from claude_proxy.proxy.app import create_app

    _host = host or settings.host
    _port = port or settings.port

    uvicorn.run(
        create_app(),
        host=_host,
        port=_port,
        log_level="info",
    )


@app.command()
def tui() -> None:
    """Open the live Textual dashboard."""
    from claude_proxy.cli.tui.dashboard import Dashboard

    Dashboard().run()


if __name__ == "__main__":
    app()
