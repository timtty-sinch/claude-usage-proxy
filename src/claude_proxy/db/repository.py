from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from claude_proxy.db.models import ApiRequest, ApiUsage


def list_requests(
    session: Session,
    limit: int = 20,
    model: str | None = None,
) -> list[dict[str, Any]]:
    stmt = (
        select(ApiRequest, ApiUsage)
        .outerjoin(ApiUsage, ApiUsage.request_id == ApiRequest.id)
        .order_by(ApiRequest.requested_at.desc())
        .limit(limit)
    )
    if model:
        stmt = stmt.where(ApiRequest.model == model)

    rows = session.execute(stmt).all()
    result = []
    for req, usage in rows:
        result.append(
            {
                "id": req.id,
                "anthropic_request_id": req.anthropic_request_id,
                "requested_at": req.requested_at,
                "duration_ms": req.duration_ms,
                "model": req.model,
                "endpoint": req.endpoint,
                "is_streaming": req.is_streaming,
                "stop_reason": req.stop_reason,
                "http_status": req.http_status,
                "error_type": req.error_type,
                "input_tokens": usage.input_tokens if usage else 0,
                "output_tokens": usage.output_tokens if usage else 0,
                "cache_read_tokens": usage.cache_read_tokens if usage else 0,
                "cache_creation_tokens": usage.cache_creation_tokens if usage else 0,
                "total_cost_usd": usage.total_cost_usd if usage else 0.0,
                "complexity": req.complexity,
                "complexity_score": req.complexity_score,
            }
        )
    return result


def stats_summary(session: Session, days: int = 7) -> list[dict[str, Any]]:
    since = datetime.now(tz=timezone.utc) - timedelta(days=days)
    stmt = (
        select(
            ApiRequest.model,
            func.count(ApiRequest.id).label("request_count"),
            func.sum(ApiUsage.input_tokens).label("total_input_tokens"),
            func.sum(ApiUsage.output_tokens).label("total_output_tokens"),
            func.sum(ApiUsage.cache_read_tokens).label("total_cache_read_tokens"),
            func.sum(ApiUsage.cache_creation_tokens).label("total_cache_creation_tokens"),
            func.sum(ApiUsage.total_cost_usd).label("total_cost_usd"),
        )
        .join(ApiUsage, ApiUsage.request_id == ApiRequest.id)
        .where(ApiRequest.requested_at >= since)
        .group_by(ApiRequest.model)
        .order_by(func.sum(ApiUsage.total_cost_usd).desc())
    )

    rows = session.execute(stmt).all()
    return [
        {
            "model": row.model,
            "request_count": row.request_count,
            "total_input_tokens": row.total_input_tokens or 0,
            "total_output_tokens": row.total_output_tokens or 0,
            "total_cache_read_tokens": row.total_cache_read_tokens or 0,
            "total_cache_creation_tokens": row.total_cache_creation_tokens or 0,
            "total_cost_usd": row.total_cost_usd or 0.0,
        }
        for row in rows
    ]


def today_cost_by_model(session: Session) -> list[dict[str, Any]]:
    now = datetime.now(tz=timezone.utc)
    start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
    stmt = (
        select(
            ApiRequest.model,
            func.count(ApiRequest.id).label("request_count"),
            func.sum(ApiUsage.input_tokens).label("total_input_tokens"),
            func.sum(ApiUsage.output_tokens).label("total_output_tokens"),
            func.sum(ApiUsage.total_cost_usd).label("total_cost_usd"),
        )
        .join(ApiUsage, ApiUsage.request_id == ApiRequest.id)
        .where(ApiRequest.requested_at >= start_of_day)
        .group_by(ApiRequest.model)
        .order_by(func.sum(ApiUsage.total_cost_usd).desc())
    )
    rows = session.execute(stmt).all()
    return [
        {
            "model": row.model,
            "request_count": row.request_count,
            "total_input_tokens": row.total_input_tokens or 0,
            "total_output_tokens": row.total_output_tokens or 0,
            "total_cost_usd": row.total_cost_usd or 0.0,
        }
        for row in rows
    ]


def export_all(session: Session) -> list[dict[str, Any]]:
    stmt = (
        select(ApiRequest, ApiUsage)
        .outerjoin(ApiUsage, ApiUsage.request_id == ApiRequest.id)
        .order_by(ApiRequest.requested_at.desc())
    )
    rows = session.execute(stmt).all()
    result = []
    for req, usage in rows:
        result.append(
            {
                "id": req.id,
                "anthropic_request_id": req.anthropic_request_id,
                "requested_at": req.requested_at.isoformat() if req.requested_at else None,
                "completed_at": req.completed_at.isoformat() if req.completed_at else None,
                "duration_ms": req.duration_ms,
                "model": req.model,
                "endpoint": req.endpoint,
                "is_streaming": req.is_streaming,
                "stop_reason": req.stop_reason,
                "system_prompt_preview": req.system_prompt_preview,
                "first_user_message_preview": req.first_user_message_preview,
                "messages_json": req.messages_json,
                "http_status": req.http_status,
                "error_type": req.error_type,
                "error_message": req.error_message,
                "input_tokens": usage.input_tokens if usage else 0,
                "output_tokens": usage.output_tokens if usage else 0,
                "cache_read_tokens": usage.cache_read_tokens if usage else 0,
                "cache_creation_tokens": usage.cache_creation_tokens if usage else 0,
                "input_cost_usd": usage.input_cost_usd if usage else 0.0,
                "output_cost_usd": usage.output_cost_usd if usage else 0.0,
                "cache_read_cost_usd": usage.cache_read_cost_usd if usage else 0.0,
                "cache_creation_cost_usd": usage.cache_creation_cost_usd if usage else 0.0,
                "total_cost_usd": usage.total_cost_usd if usage else 0.0,
            }
        )
    return result


def complexity_by_model(session: Session, days: int = 1) -> dict[str, dict[str, int]]:
    """
    Return counts of low/med/high requests per model for the last `days` days.
    Result: {"low": {"model-a": 3, ...}, "med": {...}, "high": {...}}
    """
    since = datetime.now(tz=timezone.utc) - timedelta(days=days)
    stmt = (
        select(
            ApiRequest.model,
            ApiRequest.complexity,
            func.count(ApiRequest.id).label("cnt"),
        )
        .where(ApiRequest.requested_at >= since)
        .where(ApiRequest.complexity.isnot(None))
        .group_by(ApiRequest.model, ApiRequest.complexity)
    )
    rows = session.execute(stmt).all()

    result: dict[str, dict[str, int]] = {"low": {}, "med": {}, "high": {}}
    for model, complexity, cnt in rows:
        if complexity in result:
            result[complexity][model] = cnt
    return result
