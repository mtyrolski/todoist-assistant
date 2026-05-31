"""Structured-output helpers shared by optional LLM backends."""

from contextlib import suppress
import json
import re
from typing import TypeVar

from pydantic import BaseModel, ValidationError


T = TypeVar("T", bound=BaseModel)


def _schema_instructions(schema: type[BaseModel]) -> str:
    name = schema.__name__
    if name == "InstructionSelection":
        return "JSON only: {\"selected_ids\": [\"...\"]}. Use [] if none."
    if name == "PlannerDecision":
        return (
            "JSON only with keys: plan, action, tool_code, final_answer.\n"
            "action: \"tool\" or \"final\".\n"
            "If action=tool -> tool_code required, final_answer null.\n"
            "If action=final -> final_answer required, tool_code null.\n"
            "plan can be empty."
        )
    if name == "TaskBreakdown":
        return (
            "JSON only with a top-level `children` array. "
            "Each child object must include: `content`, `description`, `priority`, `expand`, and `children`.\n"
            "Use short imperative phrases. No markdown, no numbering, no extra keys."
        )

    field_names = list(schema.model_fields)
    if len(field_names) == 1:
        field_name = field_names[0]
        extra = " tool_code should be Python only (no markdown)." if field_name == "tool_code" else ""
        return f"JSON only with key: {field_name}. Use null if unknown.{extra}"

    schema_json = json.dumps(schema.model_json_schema(), ensure_ascii=False)
    return (
        "Return ONLY valid JSON (no markdown, no code fences, no extra keys) matching this schema:\n"
        f"{schema_json}"
    )


def _strip_markdown_code_fence(text: str) -> str:
    stripped = (text or "").strip()
    if not stripped.startswith("```"):
        return stripped

    lines = stripped.splitlines()
    if not lines or not lines[0].strip().startswith("```"):
        return stripped

    lines = lines[1:]
    while lines and lines[-1].strip().startswith("```"):
        lines = lines[:-1]
    return "\n".join(lines).strip()


def _extract_json_payload(text: str) -> str | None:
    stripped = (text or "").strip()
    decoder = json.JSONDecoder()
    for idx, char in enumerate(stripped):
        if char not in "{[":
            continue
        try:
            _, end = decoder.raw_decode(stripped[idx:])
        except json.JSONDecodeError:
            continue
        return stripped[idx: idx + end].strip()
    return None


def _try_parse_top_level_json_collection(raw: str, schema: type[T]) -> T | None:
    if schema.__name__ != "TaskBreakdown":
        return None
    with suppress(ValueError, TypeError, ValidationError):
        payload = json.loads(raw)
        if isinstance(payload, list):
            return schema.model_validate({"children": payload})
    return None


def _try_parse_structured_output(raw: str, schema: type[T]) -> T | None:
    parsed: T | None = None
    with suppress(ValidationError):
        parsed = schema.model_validate_json(raw)
    if parsed is None:
        parsed = _try_parse_top_level_json_collection(raw, schema)

    cleaned = _strip_markdown_code_fence(raw)
    if parsed is None and cleaned != raw:
        with suppress(ValidationError):
            parsed = schema.model_validate_json(cleaned)
        if parsed is None:
            parsed = _try_parse_top_level_json_collection(cleaned, schema)

    extracted = _extract_json_payload(cleaned)
    if parsed is None and extracted is not None:
        with suppress(ValidationError):
            parsed = schema.model_validate_json(extracted)
        if parsed is None:
            parsed = _try_parse_top_level_json_collection(extracted, schema)

    if parsed is None:
        parsed = _try_parse_schema_fallback(cleaned, schema)
    return parsed


def _try_parse_schema_fallback(raw: str, schema: type[T]) -> T | None:
    if schema.__name__ != "TaskBreakdown":
        return None

    content_lines = _extract_breakdown_content_lines(raw)
    if content_lines:
        with suppress(ValidationError):
            return schema.model_validate({"children": [{"content": line} for line in content_lines]})

    prefixed_lines = _extract_prefixed_breakdown_lines(raw)
    if prefixed_lines:
        with suppress(ValidationError):
            return schema.model_validate({"children": [{"content": line} for line in prefixed_lines]})

    numbered_lines = _extract_numbered_breakdown_lines(raw)
    if numbered_lines:
        with suppress(ValidationError):
            return schema.model_validate({"children": [{"content": line} for line in numbered_lines]})
    return None


def _extract_breakdown_content_lines(raw: str) -> list[str]:
    items: list[str] = []
    for stripped in _iter_breakdown_candidate_lines(raw):
        match = re.match(r"^(?:[-*]\s*)?content\s*:\s*(.+)$", stripped, flags=re.IGNORECASE)
        if match is None:
            continue
        candidate = _normalize_breakdown_line(match.group(1))
        if candidate and candidate not in items:
            items.append(candidate)
    return items


def _extract_numbered_breakdown_lines(raw: str) -> list[str]:
    ignored_prefixes = ("task:", "ancestors:", "children:", "expand:", "break down tasks:")
    items: list[str] = []
    for stripped in _iter_breakdown_candidate_lines(raw):
        lowered = stripped.lower()
        if lowered.startswith(ignored_prefixes):
            continue
        match = re.match(r"^(?:[-*]|\d+[.)])\s+(.+)$", stripped)
        if match is None:
            continue
        candidate = _normalize_breakdown_line(match.group(1))
        if candidate and candidate not in items:
            items.append(candidate)
    return items


def _extract_prefixed_breakdown_lines(raw: str) -> list[str]:
    items: list[str] = []
    for stripped in _iter_breakdown_candidate_lines(raw):
        match = re.match(
            r"^(?:sub\s*task|task|step)\s*#?\s*\d+\s*[:.)-]\s+(.+)$",
            stripped,
            flags=re.IGNORECASE,
        )
        if match is None:
            continue
        candidate = _normalize_breakdown_line(match.group(1))
        if candidate and candidate not in items:
            items.append(candidate)
    return items


def _iter_breakdown_candidate_lines(raw: str) -> list[str]:
    lines: list[str] = []
    in_code_block = False
    for line in raw.splitlines():
        stripped = line.strip()
        if stripped.startswith("```"):
            in_code_block = not in_code_block
            continue
        if in_code_block:
            continue
        normalized = re.sub(
            r"(?:\[(?:/?INST|CLS|END)\]\s*)+",
            "",
            stripped,
            flags=re.IGNORECASE,
        ).strip()
        if normalized:
            lines.append(normalized)
    return lines


def _normalize_breakdown_line(value: str) -> str | None:
    text = re.sub(r"\*\*(.*?)\*\*", r"\1", value).strip()
    text = re.sub(r"\s+", " ", text)
    return text.strip(" -:\t") or None
