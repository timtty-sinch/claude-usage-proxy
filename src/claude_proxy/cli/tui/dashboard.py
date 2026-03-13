"""Textual live dashboard for Claude usage monitoring."""

from datetime import timezone
from typing import Any, Literal

from textual_plotext import PlotextPlot
from textual.app import App, ComposeResult
from textual.command import Hit, Hits, Provider
from textual.containers import Grid, Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Checkbox, ContentSwitcher, DataTable, Footer, Header, Input, Label, Tab, Tabs

from claude_proxy.alerts import AlertEngine, fire_test_notification
from claude_proxy.db.engine import SyncSessionLocal
from claude_proxy.db.repository import (
    complexity_by_model,
    cost_over_period,
    list_requests,
    today_cost_by_model,
    tool_acceptance_stats,
)

ChartType = Literal["bar", "scatter", "line"]


_MODEL_COLORS = ["cyan", "magenta", "green", "yellow", "blue", "red", "white", "orange"]


class ComplexityChart(PlotextPlot):
    """Vertical stacked bar chart: X=complexity tier, stacked by model."""

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
            self.plt.clear_data()
            self.plt.bar(["no data"], [0])
            self.plt.title("Complexity by model (last 24h)")
            self.plt.ylim(0, 1)
            self.refresh()
            return

        series = [[data[tier].get(m, 0) for tier in tiers] for m in all_models]
        colors = [_MODEL_COLORS[i % len(_MODEL_COLORS)] for i in range(len(all_models))]
        self.plt.stacked_bar(tiers, series, labels=all_models, orientation="v", color=colors)
        self.plt.title("Complexity by model (last 24h)")
        self.plt.ylabel("requests")
        self.refresh()


class ToolAcceptanceChart(PlotextPlot):
    """Vertical stacked bar chart: X=tool name, stacked by accepted/denied."""

    DEFAULT_CSS = """
    ToolAcceptanceChart {
        border: solid $primary-darken-2;
    }
    """

    def replot(self) -> None:
        with SyncSessionLocal() as session:
            rows = tool_acceptance_stats(session, days=1)

        self.plt.clear_data()

        if not rows:
            self.plt.bar(["no data"], [0])
            self.plt.title("Tool acceptance (last 24h)")
            self.plt.ylim(0, 1)
            self.refresh()
            return

        rows = rows[:3]
        tool_names = [r["tool_name"] for r in rows]
        accepted = [r["accepted"] for r in rows]
        denied = [r["denied"] for r in rows]

        self.plt.stacked_bar(tool_names, [accepted, denied],
                             labels=["accepted", "denied"], orientation="v")
        self.plt.title("Tool acceptance (last 24h)")
        self.plt.ylabel("count")
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


ALERT_ITEMS: list[tuple[str, str]] = [
    ("cost_spike",     "Cost spike: 5-min spend > 3× rolling average"),
    ("high_request",   "Single request cost exceeds threshold"),
    ("daily_budget",   "Daily spend exceeds budget limit"),
    ("request_rate",   "Request rate spike in last minute"),
]


class AlertConfigModal(ModalScreen[dict[str, Any]]):
    """Popup dialog for enabling/disabling alert notifications."""

    DEFAULT_CSS = """
    AlertConfigModal {
        align: center middle;
    }
    AlertConfigModal > Vertical {
        width: 68;
        height: auto;
        border: solid $primary;
        background: $surface;
        padding: 1 2;
    }
    AlertConfigModal #modal-title {
        text-style: bold;
        margin-bottom: 1;
    }
    AlertConfigModal Checkbox {
        margin-bottom: 0;
    }
    AlertConfigModal .alert-row {
        height: auto;
        align: left middle;
    }
    AlertConfigModal .test-btn {
        width: 8;
        min-width: 8;
        margin-right: 1;
    }
    AlertConfigModal #cost-threshold-row {
        height: auto;
        align: left middle;
        margin-top: 1;
    }
    AlertConfigModal #cost-threshold-row Input {
        width: 8;
    }
    AlertConfigModal #cost-threshold-row Label {
        padding: 0 1;
        height: 3;
        content-align: left middle;
    }
    AlertConfigModal #close-btn {
        margin-top: 1;
        width: 100%;
    }
    """

    BINDINGS = [("escape", "close_modal", "Close")]

    def __init__(self, enabled: dict[str, Any]) -> None:
        super().__init__()
        self._enabled = enabled

    def compose(self) -> ComposeResult:
        cost_cfg: dict[str, Any] = self._enabled.get("cost_threshold", {})
        with Vertical():
            yield Label("Alert Notifications", id="modal-title")
            for alert_id, label in ALERT_ITEMS:
                with Horizontal(classes="alert-row"):
                    yield Button("Test", id=f"test-{alert_id}", classes="test-btn")
                    yield Checkbox(label, value=self._enabled.get(alert_id, False), id=alert_id)
            with Horizontal(id="cost-threshold-row"):
                yield Button("Test", id="test-cost_threshold", classes="test-btn")
                yield Checkbox(
                    "Cost over $",
                    value=cost_cfg.get("enabled", False),
                    id="cost_threshold",
                )
                yield Input(value=str(cost_cfg.get("amount", "10")), id="cost-amount", placeholder="10.00")
                yield Label("in last")
                yield Input(value=str(cost_cfg.get("hours", "24")), id="cost-hours", placeholder="24")
                yield Label("hours")
            yield Button("Close", variant="primary", id="close-btn")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        btn_id = event.button.id or ""
        if btn_id == "close-btn":
            self._save_and_dismiss()
        elif btn_id.startswith("test-"):
            alert_id = btn_id[5:]
            self._send_test(alert_id)
            event.stop()

    def _send_test(self, alert_id: str) -> None:
        labels = {aid: lbl for aid, lbl in ALERT_ITEMS}
        labels["cost_threshold"] = "Cost threshold"
        amount = self.query_one("#cost-amount", Input).value or "10"
        hours = self.query_one("#cost-hours", Input).value or "24"
        messages = {
            "cost_spike":    "5-min spend 3× above rolling average",
            "high_request":  "Single request cost ≥ $0.10",
            "daily_budget":  "Today's spend ≥ $5.00",
            "request_rate":  "Request rate 3× above hourly average",
            "cost_threshold": f"Spend ≥ ${amount} in last {hours}h",
        }
        fire_test_notification(
            f"Test: {labels.get(alert_id, alert_id)}",
            messages.get(alert_id, "Test notification"),
        )

    def action_close_modal(self) -> None:
        self._save_and_dismiss()

    def _save_and_dismiss(self) -> None:
        result: dict[str, Any] = {
            alert_id: self.query_one(f"#{alert_id}", Checkbox).value
            for alert_id, _ in ALERT_ITEMS
        }
        result["cost_threshold"] = {
            "enabled": self.query_one("#cost_threshold", Checkbox).value,
            "amount": self.query_one("#cost-amount", Input).value,
            "hours": self.query_one("#cost-hours", Input).value,
        }
        self.dismiss(result)


class DashboardCommandProvider(Provider):
    """Command palette provider for the dashboard. Commands will be added here."""

    async def search(self, query: str) -> Hits:
        matcher = self.matcher(query)
        score = matcher.match("Configure alert notifications")
        if score > 0:
            yield Hit(
                score,
                matcher.highlight("Configure alert notifications"),
                self._open_alert_config,
                help="Enable or disable notification alerts",
            )

    async def _open_alert_config(self) -> None:
        app: Dashboard = self.app  # type: ignore[assignment]
        await app.push_screen(AlertConfigModal(dict(app.alert_enabled)), app._on_alert_config)


class Dashboard(App):
    """Live dashboard: top split (complexity chart + empty), center tabbed cost charts, bottom requests."""

    TITLE = "Claude Usage Proxy — Dashboard"
    COMMANDS = App.COMMANDS | {DashboardCommandProvider}

    alert_enabled: dict[str, Any] = {
        **{alert_id: False for alert_id, _ in ALERT_ITEMS},
        "cost_threshold": {"enabled": False, "amount": "10", "hours": "24"},
    }
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
            yield ToolAcceptanceChart(id="top-right-pane")
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
        self._alert_engine = AlertEngine()
        table = self.query_one("#requests-table", DataTable)
        table.add_columns("Time", "Model", "S", "Complexity", "In", "Out", "$ Cost", "ms")
        self.call_after_refresh(self._load_data)
        self.set_interval(2.0, self._load_data)

    def on_tabs_tab_activated(self, event: Tabs.TabActivated) -> None:
        if event.tab:
            self.query_one(ContentSwitcher).current = event.tab.id

    def _load_data(self) -> None:
        self.query_one(ComplexityChart).replot()
        self.query_one(ToolAcceptanceChart).replot()

        switcher = self.query_one(ContentSwitcher)
        if switcher.current:
            for chart in self.query(f"#{switcher.current} CostChart"):
                chart.replot()

        with SyncSessionLocal() as session:
            self._alert_engine.check_and_notify(self.alert_enabled, session)
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

    def _on_alert_config(self, result: dict[str, Any] | None) -> None:
        if result is not None:
            self.alert_enabled = result

    def action_refresh(self) -> None:
        self._load_data()
