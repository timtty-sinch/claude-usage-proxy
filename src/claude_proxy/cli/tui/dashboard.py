"""Textual live dashboard for Claude usage monitoring."""

from datetime import timezone

from textual_plotext import PlotextPlot
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import DataTable, Footer, Header

from claude_proxy.db.engine import SyncSessionLocal
from claude_proxy.db.repository import complexity_by_model, list_requests, today_cost_by_model


class ComplexityChart(PlotextPlot):
    """Horizontal stacked bar chart: Y=complexity tier, stacked by model."""

    DEFAULT_CSS = """
    ComplexityChart {
        border: solid $primary-darken-2;
    }
    """

    def replot(self) -> None:
        with SyncSessionLocal() as session:
            data = complexity_by_model(session, days=1)

        # Collect all models that appear in any tier
        all_models: list[str] = []
        for tier_models in data.values():
            for m in tier_models:
                if m not in all_models:
                    all_models.append(m)

        tiers = ["low", "med", "high"]

        self.plt.clear_data()

        if not all_models:
            self.plt.title("Complexity by model (last 24h) — no data")
            self.refresh()
            return

        # Build series: one list per model, values are counts per tier
        series = [[data[tier].get(m, 0) for tier in tiers] for m in all_models]

        self.plt.stacked_bar(tiers, series, labels=all_models, orientation="h")
        self.plt.title("Complexity by model (last 24h)")
        self.plt.xlabel("requests")
        self.refresh()

    def on_mount(self) -> None:
        self.replot()


class Dashboard(App):
    """Live dashboard: top split (chart + empty), middle cost table, bottom requests."""

    TITLE = "Claude Usage Proxy — Dashboard"
    CSS = """
    Screen {
        layout: vertical;
    }
    #top-pane {
        height: 30%;
        layout: horizontal;
    }
    #complexity-pane {
        width: 1fr;
        height: 100%;
    }
    #top-right-pane {
        width: 1fr;
        height: 100%;
        border: solid $primary;
    }
    #middle-pane {
        height: 20%;
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
        with Horizontal(id="top-pane"):
            yield ComplexityChart(id="complexity-pane")
            yield Vertical(id="top-right-pane")
        with Vertical(id="middle-pane"):
            yield DataTable(id="cost-table")
        with Vertical(id="bottom-pane"):
            yield DataTable(id="requests-table")
        yield Footer()

    def on_mount(self) -> None:
        cost_table = self.query_one("#cost-table", DataTable)
        cost_table.add_columns("Model", "Reqs", "In Tokens", "Out Tokens", "Cost $")

        req_table = self.query_one("#requests-table", DataTable)
        req_table.add_columns("Time", "Model", "S", "Complexity", "In", "Out", "$ Cost", "ms")

        self._load_data()
        self.set_interval(2.0, self._load_data)

    def _load_data(self) -> None:
        self.query_one(ComplexityChart).replot()

        with SyncSessionLocal() as session:
            cost_rows = today_cost_by_model(session)
            recent = list_requests(session, limit=100)

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

        req_table = self.query_one("#requests-table", DataTable)
        req_table.clear()
        for row in recent:
            ts = row["requested_at"]
            if ts and ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            time_str = ts.strftime("%H:%M:%S") if ts else "-"
            stream_icon = "~" if row["is_streaming"] else " "
            complexity = row.get("complexity") or "—"
            req_table.add_row(
                time_str,
                row["model"],
                stream_icon,
                complexity,
                f"{row['input_tokens']:,}",
                f"{row['output_tokens']:,}",
                f"${row['total_cost_usd']:.4f}",
                str(row["duration_ms"]) if row["duration_ms"] is not None else "-",
            )
        if not recent:
            req_table.add_row("—", "—", "—", "—", "—", "—", "—", "—")

    def action_refresh(self) -> None:
        self._load_data()
