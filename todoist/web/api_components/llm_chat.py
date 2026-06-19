# pyright: reportUndefinedVariable=false
"""LLM chat helper logic for the web API compatibility facade."""

# pylint: disable=protected-access,cyclic-import,too-many-lines,undefined-variable,line-too-long

from collections.abc import Mapping, Sequence
import os
from typing import Any


def _sync_api_globals():
    from todoist.web import api as web_api

    current = globals()
    for name, value in vars(web_api).items():
        if name.startswith("__"):
            continue
        original = _ORIGINALS.get(name)
        if (
            original is not None
            and getattr(value, "_component_wrapper_for", None) == name
        ):
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
    if value in {"codex", ""}:
        return "codex"
    raise ValueError(f"Unsupported LLM backend: {value}")


def _locked_llm_chat_backend() -> str | None:
    _sync_api_globals()
    value = str(os.getenv("TODOIST_DASHBOARD_LLM_BACKEND_LOCK") or "").strip().lower()
    if not value:
        return None
    return _normalize_llm_chat_backend(value)


def _available_llm_chat_backends(backend: str) -> set[str]:
    _sync_api_globals()
    _ = backend
    return {"codex"}


def _normalize_llm_chat_device(raw: Any, *, available_devices: Sequence[str]) -> str:
    _sync_api_globals()
    value = str(raw or "").strip().lower()
    if value == "gpu":
        value = "cuda"
    if value in available_devices:
        return value
    return _LLM_CHAT_DEVICE_DEFAULT


def _resolve_codex_settings(file_values: Mapping[str, Any]) -> dict[str, Any]:
    _sync_api_globals()
    model = _coerce_model_option_id(
        os.getenv(str(EnvVar.AGENT_CODEX_MODEL))
        or file_values.get(str(EnvVar.AGENT_CODEX_MODEL)),
        options=_CODEX_MODEL_OPTIONS,
        default=DEFAULT_CODEX_MODEL,
    )
    os.environ[str(EnvVar.AGENT_CODEX_MODEL)] = model
    return {
        "model": model,
        "modelOptions": _llm_model_options_payload(_CODEX_MODEL_OPTIONS, model),
    }


def _resolve_llm_chat_settings() -> dict[str, Any]:
    _sync_api_globals()
    env_path = _resolve_env_path()
    backend_key = str(EnvVar.AGENT_BACKEND)
    device_key = str(EnvVar.AGENT_DEVICE)
    file_values = dotenv_values(env_path) if env_path.exists() else {}
    available_devices = _available_llm_chat_devices()
    codex_settings = _resolve_codex_settings(file_values)

    backend = _normalize_llm_chat_backend(
        os.getenv(backend_key) or file_values.get(backend_key)
    )
    locked_backend = _locked_llm_chat_backend()
    if locked_backend:
        backend = locked_backend
    available_backend_ids = _available_llm_chat_backends(backend)
    device = _normalize_llm_chat_device(
        os.getenv(device_key) or file_values.get(device_key),
        available_devices=available_devices,
    )
    os.environ[backend_key] = backend
    os.environ[device_key] = device
    selected_model_id = codex_settings["model"]

    return {
        "backend": backend,
        "backendLabel": _LLM_CHAT_BACKEND_LABELS[backend],
        "lockedBackend": locked_backend,
        "device": device,
        "deviceLabel": _LLM_CHAT_DEVICE_LABELS[device],
        "availableBackends": [
            {
                "id": backend_id,
                "label": label,
                "available": backend_id in available_backend_ids,
            }
            for backend_id, label in _LLM_CHAT_BACKEND_LABELS.items()
            if backend_id in available_backend_ids
        ],
        "availableDevices": [
            {
                "id": device_id,
                "label": label,
                "available": device_id in available_devices,
            }
            for device_id, label in _LLM_CHAT_DEVICE_LABELS.items()
        ],
        "codex": codex_settings,
        "usage": load_llm_usage_summary(
            selected_backend=backend,
            selected_model_id=str(selected_model_id or ""),
        ),
        "envPath": _safe_display_path(env_path, root=_REPO_ROOT),
    }


def _public_llm_chat_settings(settings: dict[str, Any]) -> dict[str, Any]:
    _sync_api_globals()
    public = dict(settings)
    return public


def _build_llm_from_settings(settings: Mapping[str, Any]) -> Any:
    _sync_api_globals()
    backend = str(settings.get("backend") or _LLM_CHAT_BACKEND_DEFAULT)
    if backend == "codex":
        env_path = _resolve_env_path()
        values = dotenv_values(env_path) if env_path.exists() else {}
        return build_codex_chat_model(values, cwd=_REPO_ROOT)

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


def _assistant_metadata_payload() -> dict[str, Any]:
    _sync_api_globals()
    from todoist.agent.productivity_context import build_productivity_context

    ctx = build_productivity_context(
        cache_path=os.getenv(str(EnvVar.AGENT_CACHE_PATH), None),
        repo_root=_REPO_ROOT,
        env_path=_resolve_env_path(),
    )
    return {
        "mode": "codex",
        "tools": [
            "cache_summary()",
            "load_cache(name)",
            "script_catalog()",
            "run_script(name, args=None)",
            "llm_usage()",
            "telemetry_status()",
            "projects()",
            "create_tasks(project_id, tasks, confirmation='CREATE_TODOIST_TASKS')",
        ],
        "scripts": ctx.script_catalog(),
        "telemetry": ctx.telemetry_status(),
    }


async def _llm_chat_snapshot() -> dict[str, Any]:
    _sync_api_globals()
    enabled, loading = await _llm_chat_model_status()
    settings = _resolve_llm_chat_settings()
    async with _LLM_CHAT_STORAGE_LOCK:
        conversations = _load_llm_chat_conversations()

    summaries = [_conversation_summary(conv) for conv in conversations]
    summaries.sort(key=lambda item: item.get("updatedAt") or "", reverse=True)
    return {
        "enabled": enabled,
        "loading": loading,
        "backend": {
            "selected": settings["backend"],
            "label": settings["backendLabel"],
            "active": settings["backend"] if enabled or loading else None,
            "locked": settings["lockedBackend"],
            "options": settings["availableBackends"],
            "codex": settings["codex"],
            "envPath": settings["envPath"],
        },
        "model": {
            "selected": (
                settings["codex"]["model"]
            ),
            "label": settings["codex"]["model"],
            "active": (
                settings["codex"]["model"]
                if enabled or loading
                else None
            ),
            "codex": {
                "selected": settings["codex"]["model"],
                "options": settings["codex"]["modelOptions"],
            },
            "envPath": settings["envPath"],
        },
        "device": {
            "selected": settings["device"],
            "label": settings["deviceLabel"],
            "active": (None),
            "options": settings["availableDevices"],
            "envPath": settings["envPath"],
        },
        "usage": settings["usage"],
        "assistant": _assistant_metadata_payload(),
        "conversations": summaries,
    }


_COMPONENT_EXPORTS = (
    "_available_llm_chat_devices",
    "_build_chat_messages",
    "_build_llm_from_settings",
    "_conversation_summary",
    "_assistant_metadata_payload",
    "_llm_chat_snapshot",
    "_llm_model_options_payload",
    "_load_llm_chat_conversations",
    "_normalize_chat_conversation",
    "_normalize_chat_message",
    "_normalize_llm_chat_backend",
    "_normalize_llm_chat_device",
    "_public_llm_chat_settings",
    "_resolve_codex_settings",
    "_resolve_llm_chat_settings",
    "_save_llm_chat_conversations",
    "_truncate_text",
)
_ORIGINALS = {name: globals()[name] for name in _COMPONENT_EXPORTS}
