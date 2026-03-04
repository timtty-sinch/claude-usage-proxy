"""Parse request and response bodies for Claude API calls."""

from typing import Any


def extract_request_info(body: dict[str, Any]) -> dict[str, Any]:
    """Extract preview fields from a request body."""
    system_preview: str | None = None
    first_user_preview: str | None = None

    # Extract system prompt preview
    system = body.get("system")
    if isinstance(system, str):
        system_preview = system[:500]
    elif isinstance(system, list):
        for block in system:
            if isinstance(block, dict) and block.get("type") == "text":
                system_preview = block.get("text", "")[:500]
                break

    # Extract first user message preview
    messages = body.get("messages", [])
    for msg in messages:
        if isinstance(msg, dict) and msg.get("role") == "user":
            content = msg.get("content", "")
            if isinstance(content, str):
                first_user_preview = content[:500]
            elif isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        first_user_preview = block.get("text", "")[:500]
                        break
            break

    return {
        "model": body.get("model", "unknown"),
        "is_streaming": bool(body.get("stream", False)),
        "system_prompt_preview": system_preview,
        "first_user_message_preview": first_user_preview,
    }


def extract_usage_from_response(body: dict[str, Any]) -> dict[str, Any]:
    """Extract usage, stop reason, and anthropic_id from a non-streaming response body."""
    usage = body.get("usage", {})
    return {
        "anthropic_request_id": body.get("id"),
        "stop_reason": body.get("stop_reason"),
        "input_tokens": usage.get("input_tokens", 0),
        "output_tokens": usage.get("output_tokens", 0),
        "cache_read_tokens": usage.get("cache_read_input_tokens", 0),
        "cache_creation_tokens": usage.get("cache_creation_input_tokens", 0),
    }
