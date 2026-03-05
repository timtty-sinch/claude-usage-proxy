"""Parse request and response bodies for Claude API calls."""

import json
import re
from typing import Any

# Keywords that signal instructional/constrained prompts
_INSTRUCTION_WORDS = re.compile(
    r'\b(must|should|don\'t|always|never|make sure|ensure|need to|required|'
    r'important|critical|mandatory|forbidden|prohibited|step \d|first|then|finally|'
    r'do not|do n\'t|you must|you should|please)\b',
    re.IGNORECASE,
)
_CODE_BLOCK = re.compile(r'```')
_JSON_LIKE = re.compile(r'[{}\[\]]')
_NUMBERED_LIST = re.compile(r'^\s*\d+[\.\)]\s', re.MULTILINE)
_BULLET = re.compile(r'^\s*[-*•]\s', re.MULTILINE)


def _extract_text(messages: list[dict]) -> str:
    """Flatten all message content to a single string for analysis."""
    parts = []
    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, str):
            parts.append(content)
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    parts.append(block.get("text", ""))
    return "\n".join(parts)


def calculate_complexity(messages: list[dict]) -> tuple[int, str]:
    """
    Score prompt complexity 0–100 and return (score, tier).
    Tier is 'low', 'med', or 'high'.

    Signals:
      - Length (0–35 pts): total character count across all messages
      - Turn count (0–20 pts): number of messages
      - Code/structure (0–25 pts): code blocks, JSON-like syntax, numbered/bullet lists
      - Instruction density (0–20 pts): imperative keywords and constraint phrases
    """
    if not messages:
        return 0, "low"

    text = _extract_text(messages)
    score = 0

    # Length score (0–35)
    chars = len(text)
    if chars < 200:
        score += int(chars / 200 * 10)
    elif chars < 1000:
        score += 10 + int((chars - 200) / 800 * 10)
    elif chars < 5000:
        score += 20 + int((chars - 1000) / 4000 * 10)
    else:
        score += 35

    # Turn count score (0–20)
    turns = len(messages)
    if turns == 1:
        score += 2
    elif turns <= 3:
        score += 8
    elif turns <= 6:
        score += 14
    else:
        score += 20

    # Code / structure score (0–25)
    structure = 0
    if _CODE_BLOCK.search(text):
        structure += 10
    json_density = len(_JSON_LIKE.findall(text))
    structure += min(json_density // 5, 8)
    structure += min(len(_NUMBERED_LIST.findall(text)) * 2, 5)
    structure += min(len(_BULLET.findall(text)), 2)
    score += min(structure, 25)

    # Instruction density score (0–20)
    instruction_hits = len(_INSTRUCTION_WORDS.findall(text))
    score += min(instruction_hits * 2, 20)

    score = min(score, 100)

    if score <= 12:
        tier = "low"
    elif score <= 35:
        tier = "med"
    else:
        tier = "high"

    return score, tier


def extract_request_info(body: dict[str, Any]) -> dict[str, Any]:
    """Extract preview fields and complexity from a request body."""
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

    messages_json = json.dumps(messages) if messages else None
    complexity_score, complexity = calculate_complexity(messages)

    return {
        "model": body.get("model", "unknown"),
        "is_streaming": bool(body.get("stream", False)),
        "system_prompt_preview": system_preview,
        "first_user_message_preview": first_user_preview,
        "messages_json": messages_json,
        "complexity_score": complexity_score,
        "complexity": complexity,
    }


_DENIAL_PHRASES = ("user denied", "denied tool use", "interrupted by the user", "user rejected")


def _is_denied(result: dict) -> bool:
    if result.get("is_error"):
        return True
    content = result.get("content", "")
    text = ""
    if isinstance(content, str):
        text = content
    elif isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                text += block.get("text", "")
    return any(phrase in text.lower() for phrase in _DENIAL_PHRASES)


def _input_preview(tool_input: Any) -> str | None:
    if tool_input is None:
        return None
    if isinstance(tool_input, str):
        return tool_input[:500]
    try:
        return json.dumps(tool_input)[:500]
    except (TypeError, ValueError):
        return str(tool_input)[:500]


def extract_tool_uses(messages: list[dict]) -> list[dict]:
    """
    Walk messages and match tool_use blocks (in assistant turns) with
    tool_result blocks (in subsequent user turns).

    Returns a list of dicts with keys:
      tool_use_id, tool_name, accepted, input_preview, result_preview
    """
    # Build id -> {name, input_preview} from all assistant tool_use blocks
    tool_index: dict[str, dict] = {}
    for msg in messages:
        if msg.get("role") != "assistant":
            continue
        content = msg.get("content", [])
        if not isinstance(content, list):
            continue
        for block in content:
            if isinstance(block, dict) and block.get("type") == "tool_use":
                tid = block.get("id", "")
                tool_index[tid] = {
                    "name": block.get("name", "unknown"),
                    "input_preview": _input_preview(block.get("input")),
                }

    # Match tool_result blocks in user messages
    results = []
    for msg in messages:
        if msg.get("role") != "user":
            continue
        content = msg.get("content", [])
        if not isinstance(content, list):
            continue
        for block in content:
            if isinstance(block, dict) and block.get("type") == "tool_result":
                tid = block.get("tool_use_id", "")
                meta = tool_index.get(tid)
                if meta is None:
                    continue

                raw_content = block.get("content", "")
                if isinstance(raw_content, str):
                    result_preview = raw_content[:500]
                elif isinstance(raw_content, list):
                    parts = []
                    for rb in raw_content:
                        if isinstance(rb, dict) and rb.get("type") == "text":
                            parts.append(rb.get("text", ""))
                    result_preview = " ".join(parts)[:500]
                else:
                    result_preview = None

                results.append({
                    "tool_use_id": tid,
                    "tool_name": meta["name"],
                    "accepted": not _is_denied(block),
                    "input_preview": meta["input_preview"],
                    "result_preview": result_preview,
                })

    return results


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
