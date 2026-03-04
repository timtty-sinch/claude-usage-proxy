"""Textual live dashboard for Claude usage monitoring."""

from datetime import timezone
from typing import Literal

from textual_plotext import PlotextPlot
from textual.app import App, ComposeResult
from textual.containers import Grid, Vertical
from textual.widgets import ContentSwitcher, DataTable, Footer, Header, Tab, Tabs

from claude_proxy.db.engine import SyncSessionLocal
from claude_proxy.db.repository import cost_over_period, list_requests

ChartType = Literal["bar", "scatter", "line"]

_PERIODS = [
    ("Cost — last 1h",  1,   12),
    ("Cost — last 4h",  4,   12),
    ("Cost — last 2d",  48,  12),
    ("Cost — last 5d",  120, 12),
]


class CostChart(PlotextPlot):
    """Plots cost over a time window using bar, scatter, or line."""

    DEFAULT_CSS = """
    CostChart {
        border: solid $primary-darken-2;
    }
    """

    def __init__(self, title: str, hours: float, buckets: int,
                 chart_type: ChartType = "bar", **kwargs):
        super().__init__(**kwargs)
        self._title = title
        self._hours = hours
        self._buckets = buckets
        self._chart_type = chart_type

    def replot(self) -> None:
        with SyncSessionLocal() as session:
            data = cost_over_period(session, self._hours, self._buckets)
        labels = [b["label"] for b in data]
        values = [b["cost"] for b in data]
        self.plt.clear_data()
        if self._chart_type == "bar":
            self.plt.bar(labels, values)
        elif self._chart_type == "scatter":
            self.plt.scatter(labels, values)
        else:
            self.plt.plot(labels, values)
        self.plt.title(self._title)
        self.plt.ylabel("$ cost")
        self.refresh()

    def on_mount(self) -> None:
        self.replot()


def _chart_grid(chart_type: ChartType, grid_id: str) -> Grid:
    return Grid(
        CostChart("Cost — last 1h",  hours=1,   buckets=12, chart_type=chart_type, id=f"{grid_id}-1h"),
        CostChart("Cost — last 4h",  hours=4,   buckets=12, chart_type=chart_type, id=f"{grid_id}-4h"),
        CostChart("Cost — last 2d",  hours=48,  buckets=12, chart_type=chart_type, id=f"{grid_id}-2d"),
        CostChart("Cost — last 5d",  hours=120, buckets=12, chart_type=chart_type, id=f"{grid_id}-5d"),
        id=grid_id,
    )


class Dashboard(App):
    """Live dashboard: top empty, center tabbed charts, bottom request log."""

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
    ContentSwitcher {
        height: 1fr;
    }
    Grid {
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
            yield Tabs(
                Tab("Bar charts",     id="tab-bar"),
                Tab("Scatter charts", id="tab-scatter"),
                Tab("Line charts",    id="tab-line"),
            )
            with ContentSwitcher(initial="tab-bar"):
                yield _chart_grid("bar",     "tab-bar")
                yield _chart_grid("scatter", "tab-scatter")
                yield _chart_grid("line",    "tab-line")
        with Vertical(id="bottom-pane"):
            yield DataTable(id="requests-table")
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#requests-table", DataTable)
        table.add_columns("Time", "Model", "S", "In", "Out", "$ Cost", "ms")
        self._load_requests()
        self.set_interval(2.0, self._refresh_all)

    def on_tabs_tab_activated(self, event: Tabs.TabActivated) -> None:
        if event.tab:
            self.query_one(ContentSwitcher).current = event.tab.id

    def _refresh_all(self) -> None:
        switcher = self.query_one(ContentSwitcher)
        active_grid = switcher.current
        if active_grid:
            for chart in self.query(f"#{active_grid} CostChart"):
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
