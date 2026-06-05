"""Persistent LLM usage counters shared across local AI flows."""

from collections.abc import Mapping
from datetime import datetime
from threading import Lock
from typing import Any

from todoist.core.utils import Cache


_USAGE_LOCK = Lock()
_OPERATIONS = frozenset({"chat", "structured_chat", "repair"})


def _counter_payload(payload: Mapping[str, Any] | None = None) -> dict[str, int]:
    raw = payload if isinstance(payload, Mapping) else {}
    inference_count = _coerce_int(raw.get("inference_count"))
    chat_count = _coerce_int(raw.get("chat_count"))
    structured_count = _coerce_int(raw.get("structured_count"))
    repair_count = _coerce_int(raw.get("repair_count"))
    input_tokens = _coerce_int(raw.get("input_tokens"))
    output_tokens = _coerce_int(raw.get("output_tokens"))
    total_tokens = _coerce_int(raw.get("total_tokens"))
    recomputed_total = input_tokens + output_tokens
    if total_tokens != recomputed_total:
        total_tokens = recomputed_total
    return {
        "inference_count": inference_count,
        "chat_count": chat_count,
        "structured_count": structured_count,
        "repair_count": repair_count,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
    }


def _empty_stats_payload() -> dict[str, Any]:
    return {
        "totals": _counter_payload(),
        "backends": {},
        "updated_at": None,
        "last_request": None,
    }


def _coerce_int(value: Any) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def _load_usage_payload() -> dict[str, Any]:
    try:
        payload = Cache().llm_usage_stats.load()
    except Exception:  # pragma: no cover - defensive
        payload = {}
    if not isinstance(payload, Mapping):
        return _empty_stats_payload()

    backends_raw = payload.get("backends")
    backends_payload: dict[str, Any] = {}
    if isinstance(backends_raw, Mapping):
        for backend_name, backend_value in backends_raw.items():
            if not isinstance(backend_value, Mapping):
                continue
            models_raw = backend_value.get("models")
            models_payload: dict[str, Any] = {}
            if isinstance(models_raw, Mapping):
                for model_id, model_value in models_raw.items():
                    if not isinstance(model_value, Mapping):
                        continue
                    models_payload[str(model_id)] = {
                        "totals": _counter_payload(model_value.get("totals")),
                        "updated_at": model_value.get("updated_at"),
                        "last_request": model_value.get("last_request"),
                    }
            backends_payload[str(backend_name)] = {
                "totals": _counter_payload(backend_value.get("totals")),
                "models": models_payload,
                "updated_at": backend_value.get("updated_at"),
                "last_request": backend_value.get("last_request"),
            }

    return {
        "totals": _counter_payload(payload.get("totals")),
        "backends": backends_payload,
        "updated_at": payload.get("updated_at"),
        "last_request": payload.get("last_request"),
    }


def _increment_counter(
    counter: dict[str, int], *, operation: str, input_tokens: int, output_tokens: int
) -> None:
    counter["inference_count"] += 1
    if operation == "chat":
        counter["chat_count"] += 1
    elif operation == "structured_chat":
        counter["structured_count"] += 1
    elif operation == "repair":
        counter["repair_count"] += 1
    counter["input_tokens"] += max(0, input_tokens)
    counter["output_tokens"] += max(0, output_tokens)
    counter["total_tokens"] = counter["input_tokens"] + counter["output_tokens"]


def _request_payload(
    *,
    at: str,
    backend: str,
    model_id: str,
    operation: str,
    input_tokens: int,
    output_tokens: int,
) -> dict[str, Any]:
    return {
        "at": at,
        "backend": backend,
        "model_id": model_id,
        "operation": operation,
        "input_tokens": max(0, input_tokens),
        "output_tokens": max(0, output_tokens),
        "total_tokens": max(0, input_tokens) + max(0, output_tokens),
    }


def record_llm_usage(
    *,
    backend: str,
    model_id: str,
    operation: str,
    input_tokens: int,
    output_tokens: int,
) -> None:
    normalized_backend = str(backend or "").strip() or "unknown"
    normalized_model_id = str(model_id or "").strip() or "unknown"
    normalized_operation = str(operation or "").strip().lower()
    if normalized_operation not in _OPERATIONS:
        normalized_operation = "chat"

    now = datetime.utcnow().isoformat(timespec="seconds")
    request = _request_payload(
        at=now,
        backend=normalized_backend,
        model_id=normalized_model_id,
        operation=normalized_operation,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )

    with _USAGE_LOCK:
        payload = _load_usage_payload()
        totals = _counter_payload(payload.get("totals"))
        _increment_counter(
            totals,
            operation=normalized_operation,
            input_tokens=_coerce_int(input_tokens),
            output_tokens=_coerce_int(output_tokens),
        )
        payload["totals"] = totals
        payload["updated_at"] = now
        payload["last_request"] = request

        backends = payload.setdefault("backends", {})
        backend_entry = backends.setdefault(
            normalized_backend,
            {
                "totals": _counter_payload(),
                "models": {},
                "updated_at": None,
                "last_request": None,
            },
        )
        backend_totals = _counter_payload(backend_entry.get("totals"))
        _increment_counter(
            backend_totals,
            operation=normalized_operation,
            input_tokens=_coerce_int(input_tokens),
            output_tokens=_coerce_int(output_tokens),
        )
        backend_entry["totals"] = backend_totals
        backend_entry["updated_at"] = now
        backend_entry["last_request"] = request

        models = backend_entry.setdefault("models", {})
        model_entry = models.setdefault(
            normalized_model_id,
            {"totals": _counter_payload(), "updated_at": None, "last_request": None},
        )
        model_totals = _counter_payload(model_entry.get("totals"))
        _increment_counter(
            model_totals,
            operation=normalized_operation,
            input_tokens=_coerce_int(input_tokens),
            output_tokens=_coerce_int(output_tokens),
        )
        model_entry["totals"] = model_totals
        model_entry["updated_at"] = now
        model_entry["last_request"] = request

        Cache().llm_usage_stats.save(payload)


def _public_counter_payload(
    payload: Mapping[str, Any] | None,
    *,
    backend: str | None = None,
    model_id: str | None = None,
    last_used_at: str | None = None,
) -> dict[str, Any]:
    counter = _counter_payload(payload)
    return {
        "backend": backend,
        "modelId": model_id,
        "inferenceCount": counter["inference_count"],
        "chatCount": counter["chat_count"],
        "structuredCount": counter["structured_count"],
        "repairCount": counter["repair_count"],
        "inputTokens": counter["input_tokens"],
        "outputTokens": counter["output_tokens"],
        "totalTokens": counter["total_tokens"],
        "lastUsedAt": last_used_at,
    }


def _public_request_payload(payload: Any) -> dict[str, Any] | None:
    if not isinstance(payload, Mapping):
        return None
    return {
        "at": payload.get("at"),
        "backend": payload.get("backend"),
        "modelId": payload.get("model_id"),
        "operation": payload.get("operation"),
        "inputTokens": _coerce_int(payload.get("input_tokens")),
        "outputTokens": _coerce_int(payload.get("output_tokens")),
        "totalTokens": _coerce_int(payload.get("total_tokens")),
    }


def load_llm_usage_summary(
    *, selected_backend: str, selected_model_id: str
) -> dict[str, Any]:
    payload = _load_usage_payload()
    backends = payload.get("backends")
    backend_entry = (
        backends.get(selected_backend) if isinstance(backends, Mapping) else None
    )
    models = backend_entry.get("models") if isinstance(backend_entry, Mapping) else None
    model_entry = models.get(selected_model_id) if isinstance(models, Mapping) else None
    return {
        "totals": _public_counter_payload(payload.get("totals")),
        "current": _public_counter_payload(
            model_entry.get("totals") if isinstance(model_entry, Mapping) else None,
            backend=selected_backend,
            model_id=selected_model_id,
            last_used_at=(
                str(model_entry.get("updated_at"))
                if isinstance(model_entry, Mapping) and model_entry.get("updated_at")
                else None
            ),
        ),
        "updatedAt": payload.get("updated_at"),
        "lastRequest": _public_request_payload(payload.get("last_request")),
    }
