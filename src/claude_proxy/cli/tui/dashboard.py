"""Textual live dashboard for Claude usage monitoring."""

from datetime import timezone

from textual_plotext import PlotextPlot
from textual.app import App, ComposeResult
from textual.containers import Grid, Vertical
from textual.widgets import DataTable, Footer, Header

from claude_proxy.db.engine import SyncSessionLocal
from claude_proxy.db.repository import cost_over_period, list_requests


class CostChart(PlotextPlot):
    """Bar chart showing cost bucketed over a time window."""

    DEFAULT_CSS = """
    CostChart {
        border: solid $primary-darken-2;
    }
    """

    def __init__(self, title: str, hours: float, buckets: int, **kwargs):
        super().__init__(**kwargs)
        self._title = title
        self._hours = hours
        self._buckets = buckets

    def replot(self) -> None:
        with SyncSessionLocal() as session:
            data = cost_over_period(session, self._hours, self._buckets)
        labels = [b["label"] for b in data]
        values = [b["cost"] for b in data]
        self.plt.clear_data()
        self.plt.bar(labels, values)
        self.plt.title(self._title)
        self.plt.ylabel("$ cost")
        self.refresh()

    def on_mount(self) -> None:
        self.replot()


class Dashboard(App):
    """Live dashboard: top empty, center 4 bar charts, bottom request log."""

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
    }
    #chart-grid {
        layout: grid;
        grid-size: 2 2;
        height: 100%;
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
        with Vertical(id="center-pane"):
            with Grid(id="chart-grid"):
                yield CostChart("Cost — last 1h",  hours=1,   buckets=12, id="chart-1h")
                yield CostChart("Cost — last 4h",  hours=4,   buckets=12, id="chart-4h")
                yield CostChart("Cost — last 2d",  hours=48,  buckets=12, id="chart-2d")
                yield CostChart("Cost — last 5d",  hours=120, buckets=12, id="chart-5d")
        with Vertical(id="bottom-pane"):
            yield DataTable(id="requests-table")
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#requests-table", DataTable)
        table.add_columns("Time", "Model", "S", "In", "Out", "$ Cost", "ms")
        self._load_requests()
        self.set_interval(2.0, self._refresh_all)

    def _refresh_all(self) -> None:
        for chart in self.query(CostChart):
            chart.replot()
        self._load_requests()

    def _load_requests(self) -> None:
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
        self._refresh_all()
