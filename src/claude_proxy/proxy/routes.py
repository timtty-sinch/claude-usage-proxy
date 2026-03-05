"""Wildcard proxy route — forwards all methods to the upstream Anthropic API."""

import json
import uuid
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import Response, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from claude_proxy.config import settings
from claude_proxy.db.engine import AsyncSessionLocal
from claude_proxy.db.models import ApiRequest, ApiUsage
from claude_proxy.pricing import calculate_cost
from claude_proxy.proxy.parser import extract_request_info, extract_usage_from_response
from claude_proxy.proxy.streaming import StreamCapture, capture_stream

router = APIRouter()

# Headers that must be removed before forwarding
_STRIP_REQUEST_HEADERS = {"host", "content-length", "transfer-encoding"}


def _build_upstream_headers(request: Request) -> dict[str, str]:
    headers = {}
    for k, v in request.headers.items():
        if k.lower() not in _STRIP_REQUEST_HEADERS:
            headers[k] = v
    return headers


@router.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"])
async def proxy(path: str, request: Request) -> Response:
    query_string = request.url.query
    upstream_url = f"{settings.upstream_url}/{path}"
    if query_string:
        upstream_url = f"{upstream_url}?{query_string}"
    body_bytes = await request.body()

    # Parse request body
    request_info: dict = {}
    if body_bytes:
        try:
            body_json = json.loads(body_bytes)
            request_info = extract_request_info(body_json)
        except (json.JSONDecodeError, ValueError):
            body_json = {}
    else:
        body_json = {}

    model = request_info.get("model", "unknown")
    is_streaming = request_info.get("is_streaming", False)
    endpoint = f"/{path}"

    request_id = str(uuid.uuid4())
    requested_at = datetime.now(tz=timezone.utc)

    async with AsyncSessionLocal() as db_session:
        # Persist the initial request record
        db_request = ApiRequest(
            id=request_id,
            requested_at=requested_at,
            model=model,
            endpoint=endpoint,
            is_streaming=is_streaming,
            system_prompt_preview=request_info.get("system_prompt_preview"),
            first_user_message_preview=request_info.get("first_user_message_preview"),
            messages_json=request_info.get("messages_json"),
            complexity_score=request_info.get("complexity_score"),
            complexity=request_info.get("complexity"),
        )
        db_session.add(db_request)
        await db_session.commit()

    headers = _build_upstream_headers(request)

    if is_streaming:
        return await _handle_streaming(
            upstream_url=upstream_url,
            method=request.method,
            headers=headers,
            body_bytes=body_bytes,
            request_id=request_id,
            requested_at=requested_at,
            model=model,
        )
    else:
        async with httpx.AsyncClient(timeout=300.0) as client:
            return await _handle_non_streaming(
                client=client,
                upstream_url=upstream_url,
                method=request.method,
                headers=headers,
                body_bytes=body_bytes,
                request_id=request_id,
                requested_at=requested_at,
                model=model,
            )


async def _handle_non_streaming(
    client: httpx.AsyncClient,
    upstream_url: str,
    method: str,
    headers: dict,
    body_bytes: bytes,
    request_id: str,
    requested_at: datetime,
    model: str,
) -> Response:
    try:
        upstream_response = await client.request(
            method=method,
            url=upstream_url,
            headers=headers,
            content=body_bytes,
        )
    except httpx.RequestError as exc:
        await _record_error(request_id, requested_at, str(type(exc).__name__), str(exc))
        return Response(content=b"Upstream request failed", status_code=502)

    response_body = upstream_response.content
    completed_at = datetime.now(tz=timezone.utc)
    duration_ms = int((completed_at - requested_at).total_seconds() * 1000)

    usage_info: dict = {}
    error_type: str | None = None
    error_message: str | None = None

    if upstream_response.status_code == 200:
        try:
            response_json = json.loads(response_body)
            usage_info = extract_usage_from_response(response_json)
        except (json.JSONDecodeError, ValueError):
            pass
    else:
        try:
            error_json = json.loads(response_body)
            error_obj = error_json.get("error", {})
            error_type = error_obj.get("type")
            error_message = error_obj.get("message")
        except (json.JSONDecodeError, ValueError):
            error_type = "http_error"
            error_message = response_body.decode("utf-8", errors="replace")[:500]

    async with AsyncSessionLocal() as db_session:
        db_request = await db_session.get(ApiRequest, request_id)
        if db_request:
            db_request.completed_at = completed_at
            db_request.duration_ms = duration_ms
            db_request.http_status = upstream_response.status_code
            db_request.anthropic_request_id = usage_info.get("anthropic_request_id")
            db_request.stop_reason = usage_info.get("stop_reason")
            db_request.error_type = error_type
            db_request.error_message = error_message

        if usage_info and upstream_response.status_code == 200:
            input_tokens = usage_info.get("input_tokens", 0)
            output_tokens = usage_info.get("output_tokens", 0)
            cache_read_tokens = usage_info.get("cache_read_tokens", 0)
            cache_creation_tokens = usage_info.get("cache_creation_tokens", 0)

            cost = calculate_cost(model, input_tokens, output_tokens, cache_read_tokens, cache_creation_tokens)

            db_usage = ApiUsage(
                request_id=request_id,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cache_read_tokens=cache_read_tokens,
                cache_creation_tokens=cache_creation_tokens,
                input_cost_usd=float(cost.input_cost),
                output_cost_usd=float(cost.output_cost),
                cache_read_cost_usd=float(cost.cache_read_cost),
                cache_creation_cost_usd=float(cost.cache_creation_cost),
                total_cost_usd=float(cost.total_cost),
            )
            db_session.add(db_usage)

        await db_session.commit()

    response_headers = dict(upstream_response.headers)
    response_headers.pop("content-encoding", None)
    response_headers.pop("transfer-encoding", None)
    response_headers.pop("content-length", None)

    return Response(
        content=response_body,
        status_code=upstream_response.status_code,
        headers=response_headers,
    )


async def _handle_streaming(
    upstream_url: str,
    method: str,
    headers: dict,
    body_bytes: bytes,
    request_id: str,
    requested_at: datetime,
    model: str,
) -> StreamingResponse:
    capture = StreamCapture()

    async def generate():
        nonlocal capture
        upstream_status: int = 0
        try:
            async with httpx.AsyncClient(timeout=300.0) as client:
                async with client.stream(method, upstream_url, headers=headers, content=body_bytes) as response:
                    upstream_status = response.status_code
                    async for chunk in capture_stream(response, capture):
                        yield chunk

        except httpx.RequestError as exc:
            await _record_error(request_id, requested_at, type(exc).__name__, str(exc))
            return
        except Exception as exc:
            import logging
            logging.getLogger(__name__).exception("Unexpected error in streaming generate()")
            await _record_error(request_id, requested_at, type(exc).__name__, str(exc))
            return

        # After stream completes, persist usage (outside the HTTP context)
        try:
            completed_at = datetime.now(tz=timezone.utc)
            duration_ms = int((completed_at - requested_at).total_seconds() * 1000)

            cost = calculate_cost(
                model,
                capture.input_tokens,
                capture.output_tokens,
                capture.cache_read_tokens,
                capture.cache_creation_tokens,
            )

            async with AsyncSessionLocal() as db_session:
                db_request = await db_session.get(ApiRequest, request_id)
                if db_request:
                    db_request.completed_at = completed_at
                    db_request.duration_ms = duration_ms
                    db_request.http_status = upstream_status
                    db_request.anthropic_request_id = capture.anthropic_request_id
                    db_request.stop_reason = capture.stop_reason

                db_usage = ApiUsage(
                    request_id=request_id,
                    input_tokens=capture.input_tokens,
                    output_tokens=capture.output_tokens,
                    cache_read_tokens=capture.cache_read_tokens,
                    cache_creation_tokens=capture.cache_creation_tokens,
                    input_cost_usd=float(cost.input_cost),
                    output_cost_usd=float(cost.output_cost),
                    cache_read_cost_usd=float(cost.cache_read_cost),
                    cache_creation_cost_usd=float(cost.cache_creation_cost),
                    total_cost_usd=float(cost.total_cost),
                )
                db_session.add(db_usage)
                await db_session.commit()
        except Exception:
            import logging
            logging.getLogger(__name__).exception("Failed to persist streaming usage for request %s", request_id)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"cache-control": "no-cache", "x-accel-buffering": "no"},
    )



async def _record_error(request_id: str, requested_at: datetime, error_type: str, error_message: str) -> None:
    completed_at = datetime.now(tz=timezone.utc)
    duration_ms = int((completed_at - requested_at).total_seconds() * 1000)

    async with AsyncSessionLocal() as db_session:
        db_request = await db_session.get(ApiRequest, request_id)
        if db_request:
            db_request.completed_at = completed_at
            db_request.duration_ms = duration_ms
            db_request.http_status = 502
            db_request.error_type = error_type
            db_request.error_message = error_message
        await db_session.commit()
