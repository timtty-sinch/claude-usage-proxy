"""Textual live dashboard for Claude usage monitoring."""

from datetime import timezone

from textual.app import App, ComposeResult
from textual.widgets import DataTable, Footer, Header, Label
from textual.containers import Horizontal, Vertical

from claude_proxy.db.engine import SyncSessionLocal
from claude_proxy.db.repository import list_requests, today_cost_by_model


class Dashboard(App):
    """Live dashboard showing today's usage and recent requests."""

    TITLE = "Claude Usage Proxy — Dashboard"
    CSS = """
    Screen {
        layout: vertical;
    }
    #top-row {
        height: 1fr;
        layout: horizontal;
    }
    #cost-panel {
        width: 40;
        border: solid $primary;
        padding: 0 1;
    }
    #requests-panel {
        width: 1fr;
        border: solid $primary;
        padding: 0 1;
    }
    #cost-title {
        text-style: bold;
        margin-bottom: 1;
    }
    #requests-title {
        text-style: bold;
        margin-bottom: 1;
    }
    """

    BINDINGS = [
        ("q", "quit", "Quit"),
        ("r", "refresh", "Refresh"),
    ]

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="top-row"):
            with Vertical(id="cost-panel"):
                yield Label("Cost Summary (today)", id="cost-title")
                yield DataTable(id="cost-table")
            with Vertical(id="requests-panel"):
                yield Label("Recent Requests", id="requests-title")
                yield DataTable(id="requests-table")
        yield Footer()

    def on_mount(self) -> None:
        self._setup_tables()
        self._load_data()
        self.set_interval(2.0, self._load_data)

    def _setup_tables(self) -> None:
        cost_table = self.query_one("#cost-table", DataTable)
        cost_table.add_columns("Model", "Reqs", "In", "Out", "Cost $")

        requests_table = self.query_one("#requests-table", DataTable)
        requests_table.add_columns("Time", "Model", "S", "In", "Out", "$ Cost", "ms")

    def _load_data(self) -> None:
        with SyncSessionLocal() as session:
            cost_rows = today_cost_by_model(session)
            recent = list_requests(session, limit=50)

        # Update cost table
        cost_table = self.query_one("#cost-table", DataTable)
        cost_table.clear()
        for row in cost_rows:
            cost_table.add_row(
                row["model"],
                str(row["request_count"]),
                f"{row['total_input_tokens']:,}",
                f"{row['total_output_tokens']:,}",
                f"${row['total_cost_usd']:.4f}",
            )
        if not cost_rows:
            cost_table.add_row("—", "—", "—", "—", "—")

        # Update requests table
        requests_table = self.query_one("#requests-table", DataTable)
        requests_table.clear()
        for row in recent:
            ts = row["requested_at"]
            if ts and ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            time_str = ts.strftime("%H:%M:%S") if ts else "-"
            stream_icon = "~" if row["is_streaming"] else " "
            requests_table.add_row(
                time_str,
                row["model"],
                stream_icon,
                f"{row['input_tokens']:,}",
                f"{row['output_tokens']:,}",
                f"${row['total_cost_usd']:.4f}",
                str(row["duration_ms"]) if row["duration_ms"] is not None else "-",
            )
        if not recent:
            requests_table.add_row("—", "—", "—", "—", "—", "—", "—")

    def action_refresh(self) -> None:
        self._load_data()
