# pyright: reportUndefinedVariable=false
"""LLM chat FastAPI routes."""

# pylint: disable=protected-access,cyclic-import,undefined-variable,pointless-string-statement

from typing import Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Body, Depends, HTTPException

from todoist.web.routes.common import _sync_api_globals


def _sync_llm_globals() -> None:
    _sync_api_globals(globals())


router = APIRouter(dependencies=[Depends(_sync_llm_globals)])
_MAX_CUSTOM_INSTRUCTIONS_CHARS = 12_000


def _configuration_error(exc: ValueError) -> HTTPException:
    return HTTPException(status_code=409, detail=str(exc))


def _validate_conversation_id(conversation_id: str) -> None:
    try:
        UUID(conversation_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=400, detail="Invalid conversation ID format"
        ) from exc


def _conversation_response(conversation: dict[str, Any]) -> dict[str, Any]:
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


def _find_conversation(
    conversations: list[dict[str, Any]], conversation_id: str
) -> dict[str, Any] | None:
    return next((item for item in conversations if item.get("id") == conversation_id), None)


def _append_turn_messages(
    conversation: dict[str, Any],
    messages: list[dict[str, Any]],
    *,
    created_at: str,
) -> None:
    conversation.setdefault("messages", [])
    for msg in messages:
        role = str(msg.get("role") or "")
        content = _sanitize_text(msg.get("content"))
        if role and content:
            conversation["messages"].append(
                {"role": role, "content": content, "created_at": created_at}
            )
    conversation["updated_at"] = created_at


@router.get("/api/dashboard/llm_chat", tags=["dashboard"])
async def dashboard_llm_chat() -> dict[str, Any]:
    """Return LLM chat runtime status and conversation summaries."""

    try:
        return await _llm_chat_snapshot()
    except ValueError as exc:
        raise _configuration_error(exc) from exc


@router.get("/api/llm_chat/settings", tags=["llm"])
async def llm_chat_settings() -> dict[str, Any]:
    try:
        return _public_llm_chat_settings(_resolve_llm_chat_settings())
    except ValueError as exc:
        raise _configuration_error(exc) from exc


@router.put("/api/llm_chat/settings", tags=["llm"])
async def llm_chat_update_settings(
    payload: dict[str, Any] = Body(default_factory=dict),
) -> dict[str, Any]:
    settings = _resolve_llm_chat_settings()
    requested_backend = str(payload.get("backend") or "").strip().lower()
    if requested_backend not in {item["id"] for item in settings["availableBackends"]}:
        raise HTTPException(status_code=400, detail="Unsupported LLM backend.")
    backend = _normalize_llm_chat_backend(requested_backend)

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
    device = _normalize_llm_chat_device(
        requested_device, available_devices=available_devices
    )
    codex_model = (
        _sanitize_text(payload.get("codexModel")) or settings["codex"]["model"]
    )
    codex_model_ids = {str(item["id"]) for item in settings["codex"]["modelOptions"]}
    if codex_model not in codex_model_ids:
        raise HTTPException(status_code=400, detail="Unsupported Codex model.")

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
    set_key(str(env_path), str(EnvVar.AGENT_CODEX_MODEL), codex_model)
    os.environ[str(EnvVar.AGENT_BACKEND)] = backend
    os.environ[str(EnvVar.AGENT_DEVICE)] = device
    os.environ[str(EnvVar.AGENT_CODEX_MODEL)] = codex_model

    if enabled:
        await _reset_llm_chat_runtime()

    updated = _resolve_llm_chat_settings()
    updated["enabled"] = False if enabled else enabled
    updated["loading"] = False
    updated["reloadedRequired"] = enabled
    return _public_llm_chat_settings(updated)


@router.post("/api/llm_chat/enable", tags=["llm"])
async def llm_chat_enable() -> dict[str, Any]:
    """Start loading the local LLM model used for chat."""

    settings = _resolve_llm_chat_settings()
    if settings["backend"] == "disabled":
        raise HTTPException(status_code=400, detail="AI backend is disabled.")
    await _start_llm_chat_model_load()
    enabled, loading = await _llm_chat_model_status()
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
    """Run an interactive Codex assistant turn and return the updated conversation."""

    message = _sanitize_text(payload.get("message"))
    if not message:
        raise HTTPException(status_code=400, detail="message is required")

    settings = _resolve_llm_chat_settings()
    if settings["backend"] != "codex":
        raise HTTPException(
            status_code=409,
            detail="Codex assistant backend is required.",
        )

    conversation_id = _sanitize_text(
        payload.get("conversationId") or payload.get("conversation_id")
    )
    now = _now_iso()
    created_conversation = False

    async with _LLM_CHAT_STORAGE_LOCK:
        conversations = _load_llm_chat_conversations()
        conversation = None
        if conversation_id:
            conversation = _find_conversation(conversations, conversation_id)
            if conversation is None:
                raise HTTPException(status_code=404, detail="Conversation not found")
        else:
            conversation_id = str(uuid4())
            created_conversation = True
            title = _truncate_text(message, 80)
            conversation = {
                "id": conversation_id,
                "title": title,
                "created_at": now,
                "updated_at": now,
                "messages": [],
            }
            conversations.append(conversation)

        _save_llm_chat_conversations(conversations)

    async with _LLM_CHAT_ACTIVE_TURNS_LOCK:
        _LLM_CHAT_ACTIVE_TURNS[conversation_id] = {
            "conversationId": conversation_id,
            "message": message,
            "startedAt": now,
        }

    try:
        new_messages = await _run_llm_chat_turn(conversation, message)
    except Exception as exc:  # pragma: no cover - defensive API boundary
        if created_conversation:
            async with _LLM_CHAT_STORAGE_LOCK:
                conversations = _load_llm_chat_conversations()
                _save_llm_chat_conversations(
                    [
                        item
                        for item in conversations
                        if item.get("id") != conversation_id
                    ]
                )
        async with _LLM_CHAT_ACTIVE_TURNS_LOCK:
            _LLM_CHAT_ACTIVE_TURNS.pop(conversation_id, None)
        raise HTTPException(
            status_code=500,
            detail=f"Assistant turn failed: {type(exc).__name__}: {exc}",
        ) from exc

    finished_at = _now_iso()
    async with _LLM_CHAT_STORAGE_LOCK:
        conversations = _load_llm_chat_conversations()
        found_conversation = False
        for item in conversations:
            if item.get("id") != conversation_id:
                continue
            found_conversation = True
            _append_turn_messages(item, new_messages, created_at=finished_at)
            conversation = item
            break
        if not found_conversation:
            _append_turn_messages(conversation, new_messages, created_at=finished_at)
            conversations.append(conversation)
        _save_llm_chat_conversations(conversations)

    async with _LLM_CHAT_ACTIVE_TURNS_LOCK:
        _LLM_CHAT_ACTIVE_TURNS.pop(conversation_id, None)

    return {
        "conversationId": conversation_id,
        "conversation": _conversation_response(conversation),
    }


@router.put("/api/llm_chat/instructions", tags=["llm"])
async def llm_chat_update_instructions(
    payload: dict[str, Any] = Body(default_factory=dict),
) -> dict[str, str]:
    raw = payload.get("instructions", "")
    if not isinstance(raw, str):
        raise HTTPException(status_code=400, detail="instructions must be text")
    if len(raw) > _MAX_CUSTOM_INSTRUCTIONS_CHARS:
        raise HTTPException(
            status_code=400,
            detail=f"instructions must be at most {_MAX_CUSTOM_INSTRUCTIONS_CHARS} characters",
        )
    try:
        instructions = _save_custom_assistant_instructions(raw)
    except OSError as exc:
        raise HTTPException(
            status_code=500, detail="Could not save assistant instructions"
        ) from exc
    return {"instructions": instructions}


@router.get("/api/llm_chat/conversations/{conversation_id}", tags=["llm"])
async def llm_chat_conversation(conversation_id: str) -> dict[str, Any]:
    """Fetch a conversation transcript."""

    _validate_conversation_id(conversation_id)

    async with _LLM_CHAT_STORAGE_LOCK:
        conversations = _load_llm_chat_conversations()
    conversation = _find_conversation(conversations, conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return _conversation_response(conversation)


@router.patch("/api/llm_chat/conversations/{conversation_id}", tags=["llm"])
async def llm_chat_rename_conversation(
    conversation_id: str,
    payload: dict[str, Any] = Body(default_factory=dict),
) -> dict[str, Any]:
    _validate_conversation_id(conversation_id)
    title = _sanitize_text(payload.get("title"))
    if not title:
        raise HTTPException(status_code=400, detail="title is required")
    title = _truncate_text(title, 120)

    async with _LLM_CHAT_STORAGE_LOCK:
        conversations = _load_llm_chat_conversations()
        conversation = _find_conversation(conversations, conversation_id)
        if conversation is None:
            raise HTTPException(status_code=404, detail="Conversation not found")
        conversation["title"] = title
        conversation["updated_at"] = _now_iso()
        _save_llm_chat_conversations(conversations)
    return _conversation_response(conversation)


@router.delete("/api/llm_chat/conversations/{conversation_id}", tags=["llm"])
async def llm_chat_delete_conversation(conversation_id: str) -> dict[str, Any]:
    _validate_conversation_id(conversation_id)

    async with _LLM_CHAT_STORAGE_LOCK:
        conversations = _load_llm_chat_conversations()
        remaining = [
            item for item in conversations if item.get("id") != conversation_id
        ]
        if len(remaining) == len(conversations):
            raise HTTPException(status_code=404, detail="Conversation not found")
        _save_llm_chat_conversations(remaining)
    return {"deleted": True, "conversationId": conversation_id}
