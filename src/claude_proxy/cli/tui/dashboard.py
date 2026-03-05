"""Textual live dashboard for Claude usage monitoring."""

from datetime import timezone
from typing import Literal

from textual_plotext import PlotextPlot
from textual.app import App, ComposeResult
from textual.containers import Grid, Horizontal, Vertical
from textual.widgets import ContentSwitcher, DataTable, Footer, Header, Tab, Tabs

from claude_proxy.db.engine import SyncSessionLocal
from claude_proxy.db.repository import (
    complexity_by_model,
    cost_over_period,
    list_requests,
    today_cost_by_model,
)

ChartType = Literal["bar", "scatter", "line"]


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

        series = [[data[tier].get(m, 0) for tier in tiers] for m in all_models]
        self.plt.stacked_bar(tiers, series, labels=all_models, orientation="h")
        self.plt.title("Complexity by model (last 24h)")
        self.plt.xlabel("requests")
        self.refresh()


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
        x = list(range(len(labels)))
        self.plt.clear_data()
        if self._chart_type == "bar":
            self.plt.bar(x, values)
        elif self._chart_type == "scatter":
            self.plt.scatter(x, values)
        else:
            self.plt.plot(x, values)
        self.plt.xticks(x, labels)
        self.plt.title(self._title)
        self.plt.ylabel("$ cost")
        self.refresh()

    def on_mount(self) -> None:
        self.replot()


def _chart_grid(chart_type: ChartType, grid_id: str) -> Grid:
    return Grid(
        CostChart("Cost — last 15m", hours=0.25, buckets=15, chart_type=chart_type, id=f"{grid_id}-15m"),
        CostChart("Cost — last 30m", hours=0.5,  buckets=15, chart_type=chart_type, id=f"{grid_id}-30m"),
        CostChart("Cost — last 3h",  hours=3,    buckets=12, chart_type=chart_type, id=f"{grid_id}-3h"),
        CostChart("Cost — last 3d",  hours=72,   buckets=12, chart_type=chart_type, id=f"{grid_id}-3d"),
        id=grid_id,
    )


class Dashboard(App):
    """Live dashboard: top split (complexity chart + empty), center tabbed cost charts, bottom requests."""

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
        with Horizontal(id="top-pane"):
            yield ComplexityChart(id="complexity-pane")
            yield Vertical(id="top-right-pane")
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
        table.add_columns("Time", "Model", "S", "Complexity", "In", "Out", "$ Cost", "ms")
        self.call_after_refresh(self._load_data)
        self.set_interval(2.0, self._load_data)

    def on_tabs_tab_activated(self, event: Tabs.TabActivated) -> None:
        if event.tab:
            self.query_one(ContentSwitcher).current = event.tab.id

    def _load_data(self) -> None:
        self.query_one(ComplexityChart).replot()

        switcher = self.query_one(ContentSwitcher)
        if switcher.current:
            for chart in self.query(f"#{switcher.current} CostChart"):
                chart.replot()

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
            complexity = row.get("complexity") or "—"
            table.add_row(
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
            table.add_row("—", "—", "—", "—", "—", "—", "—", "—")

    def action_refresh(self) -> None:
        self._load_data()
