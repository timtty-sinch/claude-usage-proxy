"""SSE passthrough with usage extraction for streaming responses."""

import json
from collections.abc import AsyncIterator
from typing import Any

import httpx


async def stream_and_capture(
    response: httpx.Response,
) -> AsyncIterator[bytes]:
    """
    Yields raw SSE bytes as they arrive while capturing usage data.
    After the stream ends, the captured data is available via the
    returned StreamCapture object.
    """
    capture = StreamCapture()

    async for line in response.aiter_lines():
        raw = (line + "\n").encode()
        yield raw
        capture.process_line(line)

    # Signal end of stream
    yield b""
    # Store capture on the generator for caller to access (not straightforward with async gen)
    # Instead we use a wrapper approach below


class StreamCapture:
    """Captures SSE events to extract usage data."""

    def __init__(self) -> None:
        self.anthropic_request_id: str | None = None
        self.stop_reason: str | None = None
        self.input_tokens: int = 0
        self.output_tokens: int = 0
        self.cache_read_tokens: int = 0
        self.cache_creation_tokens: int = 0
        self._pending_data: str | None = None

    def process_line(self, line: str) -> None:
        line = line.strip()
        if line.startswith("event:"):
            self._pending_data = None
        elif line.startswith("data:"):
            raw_data = line[5:].strip()
            if raw_data == "[DONE]":
                return
            try:
                data: dict[str, Any] = json.loads(raw_data)
            except (json.JSONDecodeError, ValueError):
                return

            event_type = data.get("type")

            if event_type == "message_start":
                msg = data.get("message", {})
                self.anthropic_request_id = msg.get("id")
                usage = msg.get("usage", {})
                self.input_tokens = usage.get("input_tokens", 0)
                self.cache_read_tokens = usage.get("cache_read_input_tokens", 0)
                self.cache_creation_tokens = usage.get("cache_creation_input_tokens", 0)

            elif event_type == "message_delta":
                delta = data.get("delta", {})
                if "stop_reason" in delta:
                    self.stop_reason = delta["stop_reason"]
                usage = data.get("usage", {})
                if "output_tokens" in usage:
                    self.output_tokens = usage["output_tokens"]

            elif event_type == "message_stop":
                pass  # nothing additional needed


async def capture_stream(
    response: httpx.Response,
    capture: StreamCapture,
) -> AsyncIterator[bytes]:
    """
    Yields raw SSE bytes while populating a StreamCapture instance.
    Usage:
        capture = StreamCapture()
        async for chunk in capture_stream(response, capture):
            yield chunk
        # capture now has usage data
    """
    async for line in response.aiter_lines():
        raw = (line + "\n").encode()
        capture.process_line(line)
        yield raw
