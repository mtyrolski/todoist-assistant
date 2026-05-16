# pyright: reportUndefinedVariable=false
"""LLM chat helper logic for the web API compatibility facade."""

# pylint: disable=protected-access,cyclic-import,too-many-lines,undefined-variable,line-too-long

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta
import os
from typing import Any


def _sync_api_globals():
    from todoist.web import api as web_api

    current = globals()
    for name, value in vars(web_api).items():
        if name.startswith("__"):
            continue
        original = _ORIGINALS.get(name)
        if original is not None and getattr(value, "_component_wrapper_for", None) == name:
            current[name] = original
        else:
            current[name] = value
    return web_api

def _normalize_chat_message(raw: Any) -> dict[str, Any] | None:
    _sync_api_globals()
    if not isinstance(raw, dict):
        return None
    role = str(raw.get("role") or "").strip().lower()
    if role not in _CHAT_ROLES:
        return None
    content = _sanitize_text(raw.get("content"))
    if not content:
        return None
    created_at = str(raw.get("created_at") or raw.get("createdAt") or "")
    return {"role": role, "content": content, "created_at": created_at}
def _normalize_chat_conversation(raw: Any) -> dict[str, Any] | None:
    _sync_api_globals()
    if not isinstance(raw, dict):
        return None
    conv_id = str(raw.get("id") or "").strip()
    if not conv_id:
        return None
    title = _sanitize_text(raw.get("title")) or "Untitled chat"
    created_at = str(raw.get("created_at") or raw.get("createdAt") or "")
    updated_at = str(raw.get("updated_at") or raw.get("updatedAt") or created_at or "")
    messages_raw = raw.get("messages")
    messages: list[dict[str, Any]] = []
    if isinstance(messages_raw, list):
        for msg in messages_raw:
            normalized = _normalize_chat_message(msg)
            if normalized:
                messages.append(normalized)
    return {
        "id": conv_id,
        "title": title,
        "created_at": created_at,
        "updated_at": updated_at,
        "messages": messages,
    }
def _normalize_chat_queue_item(raw: Any) -> dict[str, Any] | None:
    _sync_api_globals()
    if not isinstance(raw, dict):
        return None
    item_id = str(raw.get("id") or "").strip()
    conversation_id = str(
        raw.get("conversation_id") or raw.get("conversationId") or ""
    ).strip()
    content = _sanitize_text(raw.get("content"))
    if not item_id or not conversation_id or not content:
        return None
    status = str(raw.get("status") or "queued").strip().lower()
    if status not in _CHAT_QUEUE_STATUSES:
        status = "queued"
    created_at = str(raw.get("created_at") or raw.get("createdAt") or "")
    return {
        "id": item_id,
        "conversation_id": conversation_id,
        "content": content,
        "status": status,
        "created_at": created_at,
        "started_at": raw.get("started_at") or raw.get("startedAt"),
        "finished_at": raw.get("finished_at") or raw.get("finishedAt"),
        "error": raw.get("error"),
    }
def _load_llm_chat_conversations() -> list[dict[str, Any]]:
    _sync_api_globals()
    try:
        payload = Cache().llm_chat_conversations.load()
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning(f"Failed to load LLM chat conversations: {exc}")
        return []
    if not isinstance(payload, list):
        return []
    conversations: list[dict[str, Any]] = []
    for raw in payload:
        normalized = _normalize_chat_conversation(raw)
        if normalized:
            conversations.append(normalized)
    return conversations
def _save_llm_chat_conversations(conversations: list[dict[str, Any]]) -> None:
    _sync_api_globals()
    try:
        Cache().llm_chat_conversations.save(conversations)
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning(f"Failed to save LLM chat conversations: {exc}")
def _load_llm_chat_queue() -> list[dict[str, Any]]:
    _sync_api_globals()
    try:
        payload = Cache().llm_chat_queue.load()
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning(f"Failed to load LLM chat queue: {exc}")
        return []
    if not isinstance(payload, list):
        return []
    queue_items: list[dict[str, Any]] = []
    for raw in payload:
        normalized = _normalize_chat_queue_item(raw)
        if normalized:
            queue_items.append(normalized)
    return queue_items
def _save_llm_chat_queue(items: list[dict[str, Any]]) -> None:
    _sync_api_globals()
    try:
        Cache().llm_chat_queue.save(items)
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning(f"Failed to save LLM chat queue: {exc}")
def _truncate_text(value: str, limit: int = 120) -> str:
    _sync_api_globals()
    if len(value) <= limit:
        return value
    return value[: max(0, limit - 3)].rstrip() + "..."
def _conversation_summary(conv: dict[str, Any]) -> dict[str, Any]:
    _sync_api_globals()
    messages = conv.get("messages") or []
    last_message = None
    if messages:
        last_message = messages[-1].get("content")
        if isinstance(last_message, str):
            last_message = _truncate_text(last_message, 140)
        else:
            last_message = None
    return {
        "id": conv.get("id"),
        "title": conv.get("title"),
        "createdAt": conv.get("created_at"),
        "updatedAt": conv.get("updated_at"),
        "messageCount": len(messages),
        "lastMessage": last_message,
    }
def _queue_item_payload(item: dict[str, Any]) -> dict[str, Any]:
    _sync_api_globals()
    return {
        "id": item.get("id"),
        "conversationId": item.get("conversation_id"),
        "content": _truncate_text(item.get("content") or "", 160),
        "status": item.get("status"),
        "createdAt": item.get("created_at"),
        "startedAt": item.get("started_at"),
        "finishedAt": item.get("finished_at"),
        "error": item.get("error"),
    }
def _parse_iso_timestamp(value: Any) -> datetime | None:
    _sync_api_globals()
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None
def _expire_llm_chat_queue(queue: list[dict[str, Any]], now_dt: datetime) -> bool:
    _sync_api_globals()
    changed = False
    cutoff = now_dt - timedelta(seconds=_LLM_CHAT_TIMEOUT_S)
    now_iso = now_dt.isoformat(timespec="seconds")
    for item in queue:
        if item.get("status") != "running":
            continue
        started_at = item.get("started_at") or item.get("created_at")
        started_dt = _parse_iso_timestamp(started_at)
        if started_dt is None:
            continue
        if started_dt <= cutoff:
            item["status"] = "failed"
            item["finished_at"] = now_iso
            item["error"] = "Timed out after 1h"
            changed = True
    return changed
def _prune_queue(queue: list[dict[str, Any]]) -> list[dict[str, Any]]:
    _sync_api_globals()
    if len(queue) <= _CHAT_QUEUE_LIMIT:
        return queue
    to_drop = len(queue) - _CHAT_QUEUE_LIMIT
    if to_drop <= 0:
        return queue
    trimmed: list[dict[str, Any]] = []
    for item in queue:
        if to_drop and item.get("status") in {"done", "failed"}:
            to_drop -= 1
            continue
        trimmed.append(item)
    return trimmed
def _available_llm_chat_devices() -> list[str]:
    _sync_api_globals()
    devices = ["cpu"]
    try:
        import torch

        if torch.cuda.is_available():
            devices.append("cuda")
    except Exception:  # pragma: no cover - defensive
        pass
    return devices
def _llm_model_options_payload(
    options: Sequence[Mapping[str, str]], selected: str
) -> list[dict[str, Any]]:
    _sync_api_globals()
    seen: set[str] = set()
    payload: list[dict[str, Any]] = []
    for option in options:
        option_id = _sanitize_text(option.get("id"))
        if not option_id or option_id in seen:
            continue
        seen.add(option_id)
        payload.append(
            {
                "id": option_id,
                "label": _sanitize_text(option.get("label")) or option_id,
                "selected": option_id == selected,
            }
        )
    if selected and selected not in seen:
        payload.insert(0, {"id": selected, "label": selected, "selected": True})
    return payload
def _model_option_ids(options: Sequence[Mapping[str, str]]) -> set[str]:
    _sync_api_globals()
    return {
        option_id
        for option in options
        if (option_id := _sanitize_text(option.get("id")))
    }
def _coerce_model_option_id(
    raw: Any,
    *,
    options: Sequence[Mapping[str, str]],
    default: str,
) -> str:
    _sync_api_globals()
    model_id = _sanitize_text(raw)
    if model_id and model_id in _model_option_ids(options):
        return model_id
    return default
def _normalize_llm_chat_backend(raw: Any) -> str:
    _sync_api_globals()
    value = str(raw or "").strip().lower()
    if value in _LLM_CHAT_BACKEND_LABELS:
        return value
    return _LLM_CHAT_BACKEND_DEFAULT
def _normalize_llm_chat_device(raw: Any, *, available_devices: Sequence[str]) -> str:
    _sync_api_globals()
    value = str(raw or "").strip().lower()
    if value == "gpu":
        value = "cuda"
    if value in available_devices:
        return value
    return _LLM_CHAT_DEVICE_DEFAULT
def _resolve_openai_settings(file_values: Mapping[str, Any]) -> dict[str, Any]:
    _sync_api_globals()
    secret_key = _sanitize_text(
        os.getenv("OPEN_AI_SECRET_KEY") or file_values.get("OPEN_AI_SECRET_KEY")
    )
    key_name = _sanitize_text(
        os.getenv("OPEN_AI_KEY_NAME") or file_values.get("OPEN_AI_KEY_NAME")
    )
    model = _sanitize_text(
        os.getenv("OPEN_AI_MODEL") or file_values.get("OPEN_AI_MODEL")
    ) or DEFAULT_OPENAI_MODEL
    if secret_key:
        os.environ["OPEN_AI_SECRET_KEY"] = secret_key
    if key_name:
        os.environ["OPEN_AI_KEY_NAME"] = key_name
    os.environ["OPEN_AI_MODEL"] = model
    return {
        "configured": bool(secret_key),
        "keyName": key_name,
        "model": model,
        "modelOptions": _llm_model_options_payload(_OPENAI_MODEL_OPTIONS, model),
    }
def _resolve_triton_settings(file_values: Mapping[str, Any]) -> dict[str, Any]:
    _sync_api_globals()
    base_url = _sanitize_text(
        os.getenv(str(EnvVar.AGENT_TRITON_URL)) or file_values.get(str(EnvVar.AGENT_TRITON_URL))
    ) or DEFAULT_TRITON_URL
    model_name = _sanitize_text(
        os.getenv(str(EnvVar.AGENT_TRITON_MODEL_NAME))
        or file_values.get(str(EnvVar.AGENT_TRITON_MODEL_NAME))
    ) or DEFAULT_TRITON_MODEL_NAME
    model_id = _coerce_model_option_id(
        os.getenv(str(EnvVar.AGENT_MODEL_ID))
        or file_values.get(str(EnvVar.AGENT_MODEL_ID)),
        options=_TRITON_MODEL_OPTIONS,
        default=DEFAULT_MODEL_ID,
    )
    os.environ[str(EnvVar.AGENT_TRITON_URL)] = base_url
    os.environ[str(EnvVar.AGENT_TRITON_MODEL_NAME)] = model_name
    os.environ[str(EnvVar.AGENT_MODEL_ID)] = model_id
    return {
        "baseUrl": base_url,
        "modelName": model_name,
        "modelId": model_id,
        "modelOptions": _llm_model_options_payload(_TRITON_MODEL_OPTIONS, model_id),
    }
def _triton_ready(triton_settings: Mapping[str, Any]) -> bool:
    _sync_api_globals()
    base_url = _sanitize_text(triton_settings.get("baseUrl"))
    if not base_url:
        return False
    try:
        response = httpx.get(
            f"{base_url.rstrip('/')}/v2/health/ready",
            timeout=0.5,
        )
        response.raise_for_status()
    except (httpx.HTTPError, ValueError):
        return False
    return True
def _resolve_llm_chat_settings() -> dict[str, Any]:
    _sync_api_globals()
    env_path = _resolve_env_path()
    backend_key = str(EnvVar.AGENT_BACKEND)
    device_key = str(EnvVar.AGENT_DEVICE)
    local_model_key = str(EnvVar.AGENT_MODEL_ID)
    file_values = dotenv_values(env_path) if env_path.exists() else {}
    available_devices = _available_llm_chat_devices()
    openai_settings = _resolve_openai_settings(file_values)
    triton_settings = _resolve_triton_settings(file_values)
    local_model_id = _coerce_model_option_id(
        os.getenv(local_model_key) or file_values.get(local_model_key),
        options=_LOCAL_MODEL_OPTIONS,
        default=DEFAULT_MODEL_ID,
    )

    backend = _normalize_llm_chat_backend(
        os.getenv(backend_key) or file_values.get(backend_key)
    )
    device = _normalize_llm_chat_device(
        os.getenv(device_key) or file_values.get(device_key),
        available_devices=available_devices,
    )
    if backend == "openai" and not openai_settings["configured"]:
        backend = _LLM_CHAT_BACKEND_DEFAULT
    os.environ[backend_key] = backend
    os.environ[device_key] = device
    os.environ[local_model_key] = local_model_id
    selected_model_id = (
        openai_settings["model"]
        if backend == "openai"
        else triton_settings["modelId"]
        if backend == "triton_local"
        else local_model_id
    )

    return {
        "backend": backend,
        "backendLabel": _LLM_CHAT_BACKEND_LABELS[backend],
        "device": device,
        "deviceLabel": _LLM_CHAT_DEVICE_LABELS[device],
        "localModelId": local_model_id,
        "localModelOptions": _llm_model_options_payload(_LOCAL_MODEL_OPTIONS, local_model_id),
        "availableBackends": [
            {
                "id": backend_id,
                "label": label,
                "available": (
                    backend_id == "transformers_local"
                    or backend_id == "triton_local"
                    or (backend_id == "openai" and openai_settings["configured"])
                ),
            }
            for backend_id, label in _LLM_CHAT_BACKEND_LABELS.items()
        ],
        "availableDevices": [
            {
                "id": device_id,
                "label": label,
                "available": device_id in available_devices,
            }
            for device_id, label in _LLM_CHAT_DEVICE_LABELS.items()
        ],
        "openai": {
            "configured": openai_settings["configured"],
            "keyName": openai_settings["keyName"],
            "model": openai_settings["model"],
            "modelOptions": openai_settings["modelOptions"],
        },
        "triton": {
            "configured": True,
            "healthy": _triton_ready(triton_settings),
            "baseUrl": triton_settings["baseUrl"],
            "modelName": triton_settings["modelName"],
            "modelId": triton_settings["modelId"],
            "modelOptions": triton_settings["modelOptions"],
        },
        "usage": load_llm_usage_summary(
            selected_backend=backend,
            selected_model_id=str(selected_model_id or ""),
        ),
        "envPath": _safe_display_path(env_path, root=_REPO_ROOT),
    }
def _public_llm_chat_settings(settings: dict[str, Any]) -> dict[str, Any]:
    _sync_api_globals()
    public = dict(settings)
    openai_settings = dict(public.get("openai") or {})
    openai_settings.pop("secretKey", None)
    public["openai"] = openai_settings
    return public
def _build_llm_from_settings(
    settings: Mapping[str, Any],
    *,
    max_output_tokens: int,
) -> _LlmChatModel:
    _sync_api_globals()
    backend = str(settings.get("backend") or _LLM_CHAT_BACKEND_DEFAULT)
    if backend == "transformers_local":
        config = coerce_model_config(
            {
                "device": settings.get("device") or _LLM_CHAT_DEVICE_DEFAULT,
                "model_id": _coerce_model_option_id(
                    settings.get("localModelId"),
                    options=_LOCAL_MODEL_OPTIONS,
                    default=DEFAULT_MODEL_ID,
                ),
                "max_new_tokens": max_output_tokens,
            }
        )
        return TransformersMistral3ChatModel(config)

    if backend == "triton_local":
        triton_settings = settings.get("triton")
        if not isinstance(triton_settings, Mapping):
            raise ValueError("Triton settings are unavailable.")
        return TritonGenerateChatModel(
            TritonChatConfig(
                base_url=str(triton_settings.get("baseUrl") or DEFAULT_TRITON_URL),
                model_name=str(triton_settings.get("modelName") or DEFAULT_TRITON_MODEL_NAME),
                model_id=_coerce_model_option_id(
                    triton_settings.get("modelId"),
                    options=_TRITON_MODEL_OPTIONS,
                    default=DEFAULT_MODEL_ID,
                ),
                max_output_tokens=max_output_tokens,
            )
        )

    if backend == "openai":
        openai_settings = settings.get("openai")
        if not isinstance(openai_settings, Mapping):
            raise ValueError("OpenAI settings are unavailable.")
        secret_key = _sanitize_text(os.getenv("OPEN_AI_SECRET_KEY"))
        if not secret_key:
            raise ValueError("OpenAI backend is not configured.")
        return OpenAIResponsesChatModel(
            OpenAIChatConfig(
                api_key=secret_key,
                key_name=_sanitize_text(openai_settings.get("keyName")),
                model=str(openai_settings.get("model") or DEFAULT_OPENAI_MODEL),
                max_output_tokens=max_output_tokens,
            )
        )

    raise ValueError(f"Unsupported LLM backend: {backend}")
def _build_chat_messages(
    conversation: dict[str, Any], user_content: str
) -> list[dict[str, str]]:
    _sync_api_globals()
    messages: list[dict[str, str]] = []
    if _CHAT_SYSTEM_PROMPT:
        messages.append(
            {"role": MessageRole.SYSTEM.value, "content": _CHAT_SYSTEM_PROMPT}
        )
    for msg in conversation.get("messages") or []:
        role = msg.get("role")
        content = msg.get("content")
        # Skip system messages from history to avoid conflicts with the prepended system prompt
        if role in _CHAT_ROLES and content and role != MessageRole.SYSTEM.value:
            messages.append({"role": role, "content": str(content)})
    messages.append({"role": MessageRole.USER.value, "content": user_content})
    return messages
async def _llm_chat_snapshot() -> dict[str, Any]:
    _sync_api_globals()
    enabled, loading = await _llm_chat_model_status()
    settings = _resolve_llm_chat_settings()
    async with _LLM_CHAT_STORAGE_LOCK:
        queue = _load_llm_chat_queue()
        if _expire_llm_chat_queue(queue, datetime.now()):
            _save_llm_chat_queue(queue)
        conversations = _load_llm_chat_conversations()

    counts = {status: 0 for status in _CHAT_QUEUE_STATUSES}
    for item in queue:
        status = item.get("status")
        if status in counts:
            counts[status] += 1

    items = list(reversed(queue))[:12]
    summaries = [_conversation_summary(conv) for conv in conversations]
    summaries.sort(key=lambda item: item.get("updatedAt") or "", reverse=True)
    current = next((item for item in queue if item.get("status") == "running"), None)
    return {
        "enabled": enabled,
        "loading": loading,
        "backend": {
            "selected": settings["backend"],
            "label": settings["backendLabel"],
            "active": settings["backend"] if enabled or loading else None,
            "options": settings["availableBackends"],
            "openai": {
                "configured": settings["openai"]["configured"],
                "keyName": settings["openai"]["keyName"],
                "model": settings["openai"]["model"],
                "modelOptions": settings["openai"]["modelOptions"],
            },
            "triton": {
                "configured": settings["triton"]["configured"],
                "healthy": settings["triton"]["healthy"],
                "baseUrl": settings["triton"]["baseUrl"],
                "modelName": settings["triton"]["modelName"],
                "modelId": settings["triton"]["modelId"],
                "modelOptions": settings["triton"]["modelOptions"],
            },
            "envPath": settings["envPath"],
        },
        "model": {
            "selected": (
                settings["openai"]["model"]
                if settings["backend"] == "openai"
                else settings["triton"]["modelId"]
                if settings["backend"] == "triton_local"
                else settings["localModelId"]
            ),
            "label": (
                settings["openai"]["model"]
                if settings["backend"] == "openai"
                else settings["triton"]["modelId"]
                if settings["backend"] == "triton_local"
                else settings["localModelId"]
            ),
            "active": (
                settings["openai"]["model"]
                if (enabled or loading) and settings["backend"] == "openai"
                else settings["triton"]["modelId"]
                if (enabled or loading) and settings["backend"] == "triton_local"
                else settings["localModelId"]
                if (enabled or loading) and settings["backend"] == "transformers_local"
                else None
            ),
            "local": {
                "selected": settings["localModelId"],
                "options": settings["localModelOptions"],
            },
            "openai": {
                "selected": settings["openai"]["model"],
                "options": settings["openai"]["modelOptions"],
            },
            "triton": {
                "selected": settings["triton"]["modelId"],
                "options": settings["triton"]["modelOptions"],
            },
            "envPath": settings["envPath"],
        },
        "device": {
            "selected": settings["device"],
            "label": settings["deviceLabel"],
            "active": (
                settings["device"]
                if (enabled or loading) and settings["backend"] == "transformers_local"
                else None
            ),
            "options": settings["availableDevices"],
            "envPath": settings["envPath"],
        },
        "queue": {
            "total": len(queue),
            "queued": counts["queued"],
            "running": counts["running"],
            "done": counts["done"],
            "failed": counts["failed"],
            "items": [_queue_item_payload(item) for item in items],
            "current": _queue_item_payload(current) if current else None,
        },
        "usage": settings["usage"],
        "conversations": summaries,
    }

_COMPONENT_EXPORTS = ('_available_llm_chat_devices', '_build_chat_messages', '_build_llm_from_settings', '_conversation_summary', '_expire_llm_chat_queue', '_llm_chat_snapshot', '_llm_model_options_payload', '_load_llm_chat_conversations', '_load_llm_chat_queue', '_normalize_chat_conversation', '_normalize_chat_message', '_normalize_chat_queue_item', '_normalize_llm_chat_backend', '_normalize_llm_chat_device', '_parse_iso_timestamp', '_prune_queue', '_public_llm_chat_settings', '_queue_item_payload', '_resolve_llm_chat_settings', '_resolve_openai_settings', '_resolve_triton_settings', '_save_llm_chat_conversations', '_save_llm_chat_queue', '_triton_ready', '_truncate_text')
_ORIGINALS = {name: globals()[name] for name in _COMPONENT_EXPORTS}
