"""Textual live dashboard for Claude usage monitoring."""

from datetime import timezone

from textual.app import App, ComposeResult
from textual.widgets import DataTable, Footer, Header
from textual.containers import Vertical

from claude_proxy.db.engine import SyncSessionLocal
from claude_proxy.db.repository import list_requests


class Dashboard(App):
    """Live dashboard showing recent requests."""

    TITLE = "Claude Usage Proxy — Dashboard"
    CSS = """
    Screen {
        layout: vertical;
    }
    #top-pane {
        height: 30%;
        border: solid $primary;
    }
    #center-pane {
        height: 50%;
        border: solid $primary;
    }
    #bottom-pane {
        height: 1fr;
        border: solid $primary;
    }
    """

    BINDINGS = [
        ("q", "quit", "Quit"),
        ("r", "refresh", "Refresh"),
    ]

    def compose(self) -> ComposeResult:
        yield Header()
        yield Vertical(id="top-pane")
        yield Vertical(id="center-pane")
        with Vertical(id="bottom-pane"):
            yield DataTable(id="requests-table")
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#requests-table", DataTable)
        table.add_columns("Time", "Model", "S", "In", "Out", "$ Cost", "ms")
        self._load_data()
        self.set_interval(2.0, self._load_data)

    def _load_data(self) -> None:
        with SyncSessionLocal() as session:
            recent = list_requests(session, limit=100)

        table = self.query_one("#requests-table", DataTable)
        table.clear()
        for row in recent:
            ts = row["requested_at"]
            if ts and ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            time_str = ts.strftime("%H:%M:%S") if ts else "-"
            stream_icon = "~" if row["is_streaming"] else " "
            table.add_row(
                time_str,
                row["model"],
                stream_icon,
                f"{row['input_tokens']:,}",
                f"{row['output_tokens']:,}",
                f"${row['total_cost_usd']:.4f}",
                str(row["duration_ms"]) if row["duration_ms"] is not None else "-",
            )
        if not recent:
            table.add_row("—", "—", "—", "—", "—", "—", "—")

    def action_refresh(self) -> None:
        self._load_data()
