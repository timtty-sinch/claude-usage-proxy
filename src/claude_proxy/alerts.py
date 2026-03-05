"""Alert engine: evaluates conditions against recorded usage and fires macOS notifications."""

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from claude_proxy.db.models import ApiRequest, ApiUsage

try:
    import rumps
    _RUMPS_AVAILABLE = True
except ImportError:
    _RUMPS_AVAILABLE = False

_COOLDOWN = timedelta(minutes=5)


def fire_test_notification(title: str, message: str) -> None:
    """Fire a one-off test notification immediately, bypassing the alert engine."""
    if _RUMPS_AVAILABLE:
        rumps.notification("Claude Proxy", title, message)


def _cost_in_window(session: Session, since: datetime, until: datetime) -> float:
    stmt = (
        select(func.sum(ApiUsage.total_cost_usd))
        .join(ApiRequest, ApiRequest.id == ApiUsage.request_id)
        .where(ApiRequest.requested_at >= since)
        .where(ApiRequest.requested_at < until)
    )
    return session.execute(stmt).scalar() or 0.0


def _request_count_in_window(session: Session, since: datetime, until: datetime) -> int:
    stmt = (
        select(func.count(ApiRequest.id))
        .where(ApiRequest.requested_at >= since)
        .where(ApiRequest.requested_at < until)
    )
    return session.execute(stmt).scalar() or 0


class AlertEngine:
    """Stateful engine that checks alert conditions and fires rumps notifications."""

    def __init__(self) -> None:
        self._last_fired: dict[str, datetime] = {}

    def check_and_notify(self, alert_enabled: dict[str, Any], session: Session) -> None:
        now = datetime.now(tz=timezone.utc)

        checks: list[tuple[str, Any]] = [
            ("cost_spike",    self._check_cost_spike),
            ("high_request",  self._check_high_request),
            ("daily_budget",  self._check_daily_budget),
            ("request_rate",  self._check_request_rate),
        ]
        for alert_id, check_fn in checks:
            if alert_enabled.get(alert_id) and not self._on_cooldown(alert_id, now):
                result = check_fn(session, now)
                if result:
                    self._fire(alert_id, *result, now)

        cost_cfg: dict[str, Any] = alert_enabled.get("cost_threshold", {})
        if cost_cfg.get("enabled") and not self._on_cooldown("cost_threshold", now):
            result = self._check_cost_threshold(session, now, cost_cfg)
            if result:
                self._fire("cost_threshold", *result, now)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _on_cooldown(self, alert_id: str, now: datetime) -> bool:
        last = self._last_fired.get(alert_id)
        return last is not None and (now - last) < _COOLDOWN

    def _fire(self, alert_id: str, title: str, message: str, now: datetime) -> None:
        if _RUMPS_AVAILABLE:
            rumps.notification("Claude Proxy", title, message)
        self._last_fired[alert_id] = now

    # ------------------------------------------------------------------
    # Alert conditions
    # ------------------------------------------------------------------

    def _check_cost_spike(self, session: Session, now: datetime) -> tuple[str, str] | None:
        """Cost in last 5 min > 3× the per-5-min average over the prior 55 min."""
        recent = _cost_in_window(session, now - timedelta(minutes=5), now)
        baseline = _cost_in_window(session, now - timedelta(hours=1), now - timedelta(minutes=5))
        avg = baseline / 11  # 11 × 5-min buckets in the prior 55 min
        if avg > 0 and recent > 3 * avg:
            return ("Cost spike", f"${recent:.4f} in last 5 min ({recent / avg:.1f}× avg)")
        return None

    def _check_high_request(self, session: Session, now: datetime) -> tuple[str, str] | None:
        """Any single request in the last 30 s costs ≥ $0.10."""
        stmt = (
            select(func.max(ApiUsage.total_cost_usd))
            .join(ApiRequest, ApiRequest.id == ApiUsage.request_id)
            .where(ApiRequest.requested_at >= now - timedelta(seconds=30))
        )
        max_cost = session.execute(stmt).scalar() or 0.0
        if max_cost >= 0.10:
            return ("Expensive request", f"Single request cost ${max_cost:.4f}")
        return None

    def _check_daily_budget(self, session: Session, now: datetime) -> tuple[str, str] | None:
        """Today's total spend ≥ $5.00."""
        start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
        total = _cost_in_window(session, start_of_day, now)
        if total >= 5.00:
            return ("Daily budget", f"Today's spend ${total:.2f} ≥ $5.00")
        return None

    def _check_request_rate(self, session: Session, now: datetime) -> tuple[str, str] | None:
        """Requests in the last minute > 3× the per-minute average over the last hour."""
        recent = _request_count_in_window(session, now - timedelta(minutes=1), now)
        baseline = _request_count_in_window(session, now - timedelta(hours=1), now - timedelta(minutes=1))
        avg = baseline / 59  # 59 prior 1-min buckets
        if avg > 0 and recent > 3 * avg:
            return ("Request spike", f"{recent} req/min ({recent / avg:.1f}× avg)")
        return None

    def _check_cost_threshold(
        self, session: Session, now: datetime, cfg: dict[str, Any]
    ) -> tuple[str, str] | None:
        """Total spend in the configured window exceeds the configured amount."""
        try:
            amount = float(cfg.get("amount") or "10")
            hours = float(cfg.get("hours") or "24")
        except ValueError:
            return None
        total = _cost_in_window(session, now - timedelta(hours=hours), now)
        if total >= amount:
            return ("Cost threshold", f"${total:.2f} spent in last {hours:g}h (limit ${amount:g})")
        return None
