# pyright: reportUndefinedVariable=false
"""LLM chat FastAPI routes."""

# pylint: disable=protected-access,cyclic-import,undefined-variable,pointless-string-statement

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Body, HTTPException

from todoist.web.routes.common import _sync_api_globals

router = APIRouter()

@router.get("/api/dashboard/llm_chat", tags=["dashboard"])
async def dashboard_llm_chat() -> dict[str, Any]:
    _sync_api_globals(globals())
    """Return LLM chat queue status and conversation summaries."""

    return await _llm_chat_snapshot()

@router.get("/api/llm_chat/settings", tags=["llm"])
async def llm_chat_settings() -> dict[str, Any]:
    _sync_api_globals(globals())
    return _public_llm_chat_settings(_resolve_llm_chat_settings())

@router.put("/api/llm_chat/settings", tags=["llm"])
async def llm_chat_update_settings(
    payload: dict[str, Any] = Body(default_factory=dict),
) -> dict[str, Any]:
    _sync_api_globals(globals())
    settings = _resolve_llm_chat_settings()
    requested_backend = str(payload.get("backend") or "").strip().lower()
    if requested_backend not in {item["id"] for item in settings["availableBackends"]}:
        raise HTTPException(status_code=400, detail="Unsupported LLM backend.")
    backend = _normalize_llm_chat_backend(requested_backend)
    if backend == "openai" and not settings["openai"]["configured"]:
        raise HTTPException(
            status_code=400,
            detail="OpenAI backend is not configured.",
        )

    available_devices = [
        str(item["id"])
        for item in settings["availableDevices"]
        if bool(item["available"])
    ]
    requested_device = str(payload.get("device") or "").strip().lower()
    if requested_device == "gpu":
        requested_device = "cuda"
    if requested_device not in _LLM_CHAT_DEVICE_LABELS:
        raise HTTPException(status_code=400, detail="Unsupported LLM device.")
    if requested_device not in available_devices:
        raise HTTPException(
            status_code=400,
            detail="Requested device is not available on this machine.",
        )
    device = _normalize_llm_chat_device(requested_device, available_devices=available_devices)
    local_model_id = _sanitize_text(payload.get("localModelId")) or settings["localModelId"]
    openai_model = _sanitize_text(payload.get("openaiModel")) or settings["openai"]["model"]
    triton_model_id = _sanitize_text(payload.get("tritonModelId")) or settings["triton"]["modelId"]
    local_model_ids = {str(item["id"]) for item in settings["localModelOptions"]}
    triton_model_ids = {str(item["id"]) for item in settings["triton"]["modelOptions"]}
    if local_model_id not in local_model_ids:
        raise HTTPException(status_code=400, detail="Unsupported local LLM model.")
    if triton_model_id not in triton_model_ids:
        raise HTTPException(status_code=400, detail="Unsupported Triton LLM model.")
    model_id = triton_model_id if backend == "triton_local" else local_model_id

    enabled, loading = await _llm_chat_model_status()
    if loading:
        raise HTTPException(
            status_code=409,
            detail="Cannot change LLM settings while the model is loading.",
        )

    env_path = _resolve_env_path()
    env_path.parent.mkdir(parents=True, exist_ok=True)
    set_key(str(env_path), str(EnvVar.AGENT_BACKEND), backend)
    set_key(str(env_path), str(EnvVar.AGENT_DEVICE), device)
    set_key(str(env_path), str(EnvVar.AGENT_MODEL_ID), model_id)
    set_key(str(env_path), "OPEN_AI_MODEL", openai_model)
    os.environ[str(EnvVar.AGENT_BACKEND)] = backend
    os.environ[str(EnvVar.AGENT_DEVICE)] = device
    os.environ[str(EnvVar.AGENT_MODEL_ID)] = model_id
    os.environ["OPEN_AI_MODEL"] = openai_model

    if enabled:
        await _reset_llm_chat_runtime()

    updated = _resolve_llm_chat_settings()
    updated["enabled"] = False if enabled else enabled
    updated["loading"] = False
    updated["reloadedRequired"] = enabled
    return _public_llm_chat_settings(updated)

@router.post("/api/llm_chat/enable", tags=["llm"])
async def llm_chat_enable() -> dict[str, Any]:
    _sync_api_globals(globals())
    """Start loading the local LLM model used for chat."""

    await _start_llm_chat_model_load()
    enabled, loading = await _llm_chat_model_status()
    settings = _resolve_llm_chat_settings()
    return {
        "enabled": enabled,
        "loading": loading,
        "backend": settings["backend"],
        "device": settings["device"],
    }

@router.post("/api/llm_chat/send", tags=["llm"])
async def llm_chat_send(
    payload: dict[str, Any] = Body(default_factory=dict),
) -> dict[str, Any]:
    _sync_api_globals(globals())
    """Queue a chat prompt for the local LLM."""

    message = _sanitize_text(payload.get("message"))
    if not message:
        raise HTTPException(status_code=400, detail="message is required")

    enabled, loading = await _llm_chat_model_status()
    if not (enabled or loading):
        raise HTTPException(
            status_code=409,
            detail="Model not loaded. Click Enable in the dashboard first.",
        )

    conversation_id = _sanitize_text(
        payload.get("conversationId") or payload.get("conversation_id")
    )
    now = _now_iso()

    async with _LLM_CHAT_STORAGE_LOCK:
        conversations = _load_llm_chat_conversations()
        conversation = None
        if conversation_id:
            conversation = next(
                (item for item in conversations if item.get("id") == conversation_id),
                None,
            )
            if conversation is None:
                raise HTTPException(status_code=404, detail="Conversation not found")
        else:
            conversation_id = str(uuid4())
            title = _truncate_text(message, 80)
            conversation = {
                "id": conversation_id,
                "title": title,
                "created_at": now,
                "updated_at": now,
                "messages": [],
            }
            conversations.append(conversation)

        conversation["updated_at"] = now

        queue = _load_llm_chat_queue()
        item = {
            "id": str(uuid4()),
            "conversation_id": conversation_id,
            "content": message,
            "status": "queued",
            "created_at": now,
            "started_at": None,
            "finished_at": None,
            "error": None,
        }
        queue.append(item)
        queue = _prune_queue(queue)
        _save_llm_chat_queue(queue)
        _save_llm_chat_conversations(conversations)

    if enabled or loading:
        await _maybe_start_llm_chat_worker()
    return {
        "queued": True,
        "item": _queue_item_payload(item),
        "conversationId": conversation_id,
    }

@router.get("/api/llm_chat/conversations/{conversation_id}", tags=["llm"])
async def llm_chat_conversation(conversation_id: str) -> dict[str, Any]:
    _sync_api_globals(globals())
    """Fetch a conversation transcript."""

    # Validate conversation_id format (should be a valid UUID)
    try:
        UUID(conversation_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=400, detail="Invalid conversation ID format"
        ) from exc

    async with _LLM_CHAT_STORAGE_LOCK:
        conversations = _load_llm_chat_conversations()
    conversation = next(
        (item for item in conversations if item.get("id") == conversation_id), None
    )
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {
        "id": conversation.get("id"),
        "title": conversation.get("title"),
        "createdAt": conversation.get("created_at"),
        "updatedAt": conversation.get("updated_at"),
        "messages": [
            {
                "role": msg.get("role"),
                "content": msg.get("content"),
                "createdAt": msg.get("created_at"),
            }
            for msg in conversation.get("messages") or []
        ],
    }
