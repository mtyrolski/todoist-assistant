"""Tests for FastAPI LLM chat endpoints."""

import asyncio

from fastapi.testclient import TestClient

import todoist.web.api as web_api
from todoist.core.env import EnvVar

# pylint: disable=protected-access


# LLM Chat endpoint tests


def test_dashboard_llm_chat_returns_structure(monkeypatch, tmp_path) -> None:
    """Test /api/dashboard/llm_chat returns expected structure when model not loaded."""
    monkeypatch.delenv(str(web_api.EnvVar.AGENT_BACKEND), raising=False)
    monkeypatch.delenv(str(web_api.EnvVar.AGENT_DEVICE), raising=False)
    monkeypatch.delenv(str(web_api.EnvVar.AGENT_MODEL_ID), raising=False)
    monkeypatch.setenv(str(web_api.EnvVar.CACHE_DIR), str(tmp_path))
    monkeypatch.setattr(web_api, "_resolve_env_path", lambda: tmp_path / ".env")

    # Mock the model status to be disabled
    async def _mock_model_status():
        return False, False  # enabled, loading

    monkeypatch.setattr(web_api, "_llm_chat_model_status", _mock_model_status)

    # Mock storage functions to return empty data
    monkeypatch.setattr(web_api, "_load_llm_chat_queue", lambda: [])
    monkeypatch.setattr(web_api, "_load_llm_chat_conversations", lambda: [])

    client = TestClient(web_api.app)
    res = client.get("/api/dashboard/llm_chat")
    assert res.status_code == 200
    payload = res.json()

    # Verify structure
    assert "enabled" in payload
    assert "loading" in payload
    assert "backend" in payload
    assert "device" in payload
    assert "queue" in payload
    assert "usage" in payload
    assert "conversations" in payload

    # Verify queue structure
    assert "total" in payload["queue"]
    assert "queued" in payload["queue"]
    assert "running" in payload["queue"]
    assert "done" in payload["queue"]
    assert "failed" in payload["queue"]
    assert "items" in payload["queue"]
    assert "current" in payload["queue"]

    # Verify disabled state
    assert payload["enabled"] is False
    assert payload["loading"] is False
    assert payload["backend"]["selected"] == "disabled"
    assert payload["backend"]["triton"]["configured"] is True
    assert payload["backend"]["codex"]["model"] == "gpt-5.5"
    assert payload["backend"]["triton"]["modelId"] in {
        option["id"] for option in payload["backend"]["triton"]["modelOptions"]
    }
    assert payload["model"]["selected"] == "disabled"
    assert payload["device"]["selected"] == "cpu"
    assert payload["usage"]["totals"]["inferenceCount"] == 0
    assert payload["usage"]["current"]["modelId"] == "disabled"
    assert payload["queue"]["total"] == 0
    assert payload["conversations"] == []


def test_llm_chat_update_settings_persists_env_and_resets_runtime(
    monkeypatch, tmp_path
) -> None:
    env_path = tmp_path / ".env"
    monkeypatch.setattr(web_api, "_resolve_env_path", lambda: env_path)
    monkeypatch.setattr(web_api, "_available_llm_chat_devices", lambda: ["cpu", "cuda"])
    monkeypatch.setattr(web_api, "_LLM_CHAT_MODEL", object())
    monkeypatch.setattr(web_api, "_LLM_CHAT_AGENT", object())
    monkeypatch.setattr(web_api, "_LLM_CHAT_MODEL_LOADING", False)

    client = TestClient(web_api.app)
    res = client.put(
        "/api/llm_chat/settings",
        json={
            "backend": "codex",
            "device": "cuda",
            "codexModel": "gpt-5.5",
        },
    )

    assert res.status_code == 200
    payload = res.json()
    assert payload["backend"] == "codex"
    assert payload["device"] == "cuda"
    assert payload["codex"]["model"] == "gpt-5.5"
    assert payload["reloadedRequired"] is True
    assert env_path.read_text(encoding="utf-8").find("TODOIST_AGENT_DEVICE='cuda'") >= 0
    assert (
        env_path.read_text(encoding="utf-8").find("TODOIST_AGENT_CODEX_MODEL='gpt-5.5'")
        >= 0
    )
    assert web_api._LLM_CHAT_MODEL is None
    assert web_api._LLM_CHAT_AGENT is None


def test_llm_chat_settings_response_exposes_codex_and_triton_options(
    monkeypatch, tmp_path
) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text(
        "\n".join(
            [
                "TODOIST_AGENT_CODEX_MODEL='gpt-5.5'",
                "TODOIST_AGENT_MODEL_ID='not/supported'",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(web_api, "_resolve_env_path", lambda: env_path)
    monkeypatch.setattr(web_api, "_available_llm_chat_devices", lambda: ["cpu", "cuda"])
    monkeypatch.setattr(web_api, "_triton_ready", lambda _settings: True)

    client = TestClient(web_api.app)
    res = client.get("/api/llm_chat/settings")

    assert res.status_code == 200
    payload = res.json()
    assert payload["envPath"] == ".env"
    assert payload["codex"]["model"] == "gpt-5.5"
    assert "gpt-5.5" in {option["id"] for option in payload["codex"]["modelOptions"]}
    assert [option["id"] for option in payload["triton"]["modelOptions"]] == [
        "Qwen/Qwen2.5-3B-Instruct"
    ]
    assert payload["triton"]["modelId"] == "Qwen/Qwen2.5-3B-Instruct"


def test_llm_chat_settings_lock_hides_and_rejects_triton(monkeypatch, tmp_path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text(
        "\n".join(
            [
                "TODOIST_AGENT_BACKEND='triton_local'",
                "TODOIST_AGENT_MODEL_ID='Qwen/Qwen2.5-3B-Instruct'",
                "TODOIST_AGENT_CODEX_MODEL='gpt-5.5'",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("TODOIST_DASHBOARD_LLM_BACKEND_LOCK", "codex")
    monkeypatch.setattr(web_api, "_resolve_env_path", lambda: env_path)
    monkeypatch.setattr(web_api, "_available_llm_chat_devices", lambda: ["cpu"])

    def _unexpected_triton_probe(_settings):
        raise AssertionError(
            "Triton should not be probed when the dashboard is locked to Codex"
        )

    monkeypatch.setattr(web_api, "_triton_ready", _unexpected_triton_probe)

    client = TestClient(web_api.app)
    res = client.get("/api/llm_chat/settings")

    assert res.status_code == 200
    payload = res.json()
    assert payload["backend"] == "codex"
    assert payload["lockedBackend"] == "codex"
    assert [option["id"] for option in payload["availableBackends"]] == ["codex"]
    assert payload["triton"] == {
        "configured": False,
        "healthy": False,
        "baseUrl": "",
        "modelName": "",
        "modelId": "",
        "modelOptions": [],
    }

    update = client.put(
        "/api/llm_chat/settings",
        json={"backend": "triton_local", "device": "cpu"},
    )
    assert update.status_code == 400
    assert update.json()["detail"] == "Unsupported LLM backend."


def test_llm_chat_update_settings_rejects_unavailable_device(monkeypatch) -> None:
    monkeypatch.setattr(web_api, "_available_llm_chat_devices", lambda: ["cpu"])

    client = TestClient(web_api.app)
    res = client.put(
        "/api/llm_chat/settings",
        json={"backend": "codex", "device": "cuda"},
    )

    assert res.status_code == 400


def test_llm_chat_update_settings_rejects_unsupported_codex_model(monkeypatch) -> None:
    monkeypatch.setattr(web_api, "_available_llm_chat_devices", lambda: ["cpu"])

    client = TestClient(web_api.app)
    res = client.put(
        "/api/llm_chat/settings",
        json={
            "backend": "codex",
            "device": "cpu",
            "codexModel": "not-a-codex-model",
        },
    )

    assert res.status_code == 400


def test_llm_chat_update_settings_supports_codex_backend(monkeypatch, tmp_path) -> None:
    env_path = tmp_path / ".env"
    monkeypatch.setattr(web_api, "_resolve_env_path", lambda: env_path)
    monkeypatch.setattr(web_api, "_available_llm_chat_devices", lambda: ["cpu", "cuda"])
    monkeypatch.setattr(web_api, "_LLM_CHAT_MODEL", object())
    monkeypatch.setattr(web_api, "_LLM_CHAT_AGENT", object())
    monkeypatch.setattr(web_api, "_LLM_CHAT_MODEL_LOADING", False)

    client = TestClient(web_api.app)
    res = client.put(
        "/api/llm_chat/settings",
        json={"backend": "codex", "device": "cpu", "codexModel": "gpt-5.5"},
    )

    assert res.status_code == 200
    payload = res.json()
    assert payload["backend"] == "codex"
    assert payload["codex"]["model"] == "gpt-5.5"
    assert payload["envPath"] == ".env"
    assert web_api._LLM_CHAT_MODEL is None
    assert web_api._LLM_CHAT_AGENT is None


def test_llm_chat_update_settings_supports_triton_backend(
    monkeypatch, tmp_path
) -> None:
    env_path = tmp_path / ".env"
    monkeypatch.setattr(web_api, "_resolve_env_path", lambda: env_path)
    monkeypatch.setattr(web_api, "_available_llm_chat_devices", lambda: ["cpu", "cuda"])
    monkeypatch.setattr(web_api, "_triton_ready", lambda _settings: True)
    monkeypatch.setattr(web_api, "_LLM_CHAT_MODEL", object())
    monkeypatch.setattr(web_api, "_LLM_CHAT_AGENT", object())
    monkeypatch.setattr(web_api, "_LLM_CHAT_MODEL_LOADING", False)

    client = TestClient(web_api.app)
    res = client.put(
        "/api/llm_chat/settings",
        json={
            "backend": "triton_local",
            "device": "cpu",
            "tritonModelId": "Qwen/Qwen2.5-3B-Instruct",
        },
    )

    assert res.status_code == 200
    payload = res.json()
    assert payload["backend"] == "triton_local"
    assert payload["triton"]["healthy"] is True
    assert payload["triton"]["modelName"] == "todoist_llm"
    assert payload["triton"]["modelId"] == "Qwen/Qwen2.5-3B-Instruct"
    saved = env_path.read_text(encoding="utf-8")
    assert "TODOIST_AGENT_BACKEND='triton_local'" in saved
    assert "TODOIST_AGENT_MODEL_ID='Qwen/Qwen2.5-3B-Instruct'" in saved


def test_llm_chat_send_requires_message() -> None:
    """Test /api/llm_chat/send validates message is required."""
    client = TestClient(web_api.app)
    res = client.post("/api/llm_chat/send", json={})
    assert res.status_code == 400
    payload = res.json()
    assert "message is required" in payload["detail"]


def test_llm_chat_send_requires_model_loaded(monkeypatch) -> None:
    """Test /api/llm_chat/send requires model to be loaded or loading."""

    # Mock the model status to be disabled
    async def _mock_model_status():
        return False, False  # enabled, loading

    monkeypatch.setattr(web_api, "_llm_chat_model_status", _mock_model_status)

    client = TestClient(web_api.app)
    res = client.post("/api/llm_chat/send", json={"message": "Hello"})
    assert res.status_code == 409
    payload = res.json()
    assert "Model not loaded" in payload["detail"]


def test_llm_chat_send_allows_codex_inline_without_model_loaded(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.setenv(str(EnvVar.CACHE_DIR), str(tmp_path))
    monkeypatch.setenv(str(EnvVar.AGENT_BACKEND), "codex")
    monkeypatch.setenv(str(EnvVar.AGENT_CODEX_MODEL), "gpt-5.5")
    monkeypatch.setattr(web_api, "_LLM_CHAT_MODEL", None)
    monkeypatch.setattr(web_api, "_LLM_CHAT_MODEL_LOADING", False)
    monkeypatch.setattr(web_api, "_triton_ready", lambda _settings: False)

    async def _mock_model_status():
        return False, False

    saved_queue = []
    saved_conversations = []

    def _mock_save_queue(items):
        saved_queue.clear()
        saved_queue.extend(items)

    def _mock_save_conversations(items):
        saved_conversations.clear()
        saved_conversations.extend(items)

    async def _mock_run_inline():
        saved_queue[0]["status"] = "done"
        saved_queue[0]["finished_at"] = web_api._now_iso()

    monkeypatch.setattr(web_api, "_llm_chat_model_status", _mock_model_status)
    monkeypatch.setattr(web_api, "_load_llm_chat_queue", lambda: list(saved_queue))
    monkeypatch.setattr(web_api, "_load_llm_chat_conversations", lambda: [])
    monkeypatch.setattr(web_api, "_save_llm_chat_queue", _mock_save_queue)
    monkeypatch.setattr(
        web_api, "_save_llm_chat_conversations", _mock_save_conversations
    )
    monkeypatch.setattr(web_api, "_run_llm_chat_queue_inline", _mock_run_inline)

    client = TestClient(web_api.app)
    res = client.post("/api/llm_chat/send", json={"message": "Run inline Codex"})

    assert res.status_code == 200
    assert res.json()["queued"] is True
    assert res.json()["item"]["status"] == "done"
    assert saved_queue[0]["status"] == "done"
    assert saved_conversations[0]["title"] == "Run inline Codex"


def test_llm_chat_send_creates_new_conversation(monkeypatch) -> None:
    """Test /api/llm_chat/send creates a new conversation when no conversation_id provided."""

    # Mock the model status to be enabled
    async def _mock_model_status():
        return True, False  # enabled, loading

    # Track what was saved
    saved_queue = []
    saved_conversations = []

    def _mock_save_queue(items):
        saved_queue.clear()
        saved_queue.extend(items)

    def _mock_save_conversations(items):
        saved_conversations.clear()
        saved_conversations.extend(items)

    monkeypatch.setattr(web_api, "_llm_chat_model_status", _mock_model_status)
    monkeypatch.setattr(web_api, "_load_llm_chat_queue", lambda: [])
    monkeypatch.setattr(web_api, "_load_llm_chat_conversations", lambda: [])
    monkeypatch.setattr(web_api, "_save_llm_chat_queue", _mock_save_queue)
    monkeypatch.setattr(
        web_api, "_save_llm_chat_conversations", _mock_save_conversations
    )
    monkeypatch.setattr(web_api, "_prune_queue", lambda q: q)

    # Mock worker start to do nothing
    async def _mock_start_worker():
        pass

    monkeypatch.setattr(web_api, "_maybe_start_llm_chat_worker", _mock_start_worker)

    client = TestClient(web_api.app)
    res = client.post("/api/llm_chat/send", json={"message": "Hello, world!"})
    assert res.status_code == 200
    payload = res.json()

    # Verify response structure
    assert payload["queued"] is True
    assert "item" in payload
    assert "conversationId" in payload

    # Verify a conversation was created
    assert len(saved_conversations) == 1
    conv = saved_conversations[0]
    assert conv["title"] == "Hello, world!"
    assert conv["id"] == payload["conversationId"]
    assert "created_at" in conv
    assert "updated_at" in conv
    assert conv["messages"] == []

    # Verify queue item was created
    assert len(saved_queue) == 1
    item = saved_queue[0]
    assert item["conversation_id"] == payload["conversationId"]
    assert item["content"] == "Hello, world!"
    assert item["status"] == "queued"


def test_llm_chat_send_uses_existing_conversation(monkeypatch) -> None:
    """Test /api/llm_chat/send adds to existing conversation when conversation_id provided."""

    # Mock the model status to be enabled
    async def _mock_model_status():
        return True, False  # enabled, loading

    existing_conv_id = "550e8400-e29b-41d4-a716-446655440000"
    existing_conversations = [
        {
            "id": existing_conv_id,
            "title": "Existing Chat",
            "created_at": "2025-01-01T10:00:00",
            "updated_at": "2025-01-01T10:00:00",
            "messages": [],
        }
    ]

    # Track what was saved
    saved_queue = []
    saved_conversations = []

    def _mock_save_queue(items):
        saved_queue.clear()
        saved_queue.extend(items)

    def _mock_save_conversations(items):
        saved_conversations.clear()
        saved_conversations.extend(items)

    monkeypatch.setattr(web_api, "_llm_chat_model_status", _mock_model_status)
    monkeypatch.setattr(web_api, "_load_llm_chat_queue", lambda: [])
    monkeypatch.setattr(
        web_api, "_load_llm_chat_conversations", lambda: existing_conversations[:]
    )
    monkeypatch.setattr(web_api, "_save_llm_chat_queue", _mock_save_queue)
    monkeypatch.setattr(
        web_api, "_save_llm_chat_conversations", _mock_save_conversations
    )
    monkeypatch.setattr(web_api, "_prune_queue", lambda q: q)

    # Mock worker start to do nothing
    async def _mock_start_worker():
        pass

    monkeypatch.setattr(web_api, "_maybe_start_llm_chat_worker", _mock_start_worker)

    client = TestClient(web_api.app)
    res = client.post(
        "/api/llm_chat/send",
        json={"message": "Follow up", "conversationId": existing_conv_id},
    )
    assert res.status_code == 200
    payload = res.json()

    # Verify response uses existing conversation
    assert payload["conversationId"] == existing_conv_id

    # Verify conversation was updated (not created)
    assert len(saved_conversations) == 1
    assert saved_conversations[0]["id"] == existing_conv_id
    assert saved_conversations[0]["title"] == "Existing Chat"  # Title unchanged


def test_llm_chat_send_rejects_invalid_conversation_id(monkeypatch) -> None:
    """Test /api/llm_chat/send returns 404 for non-existent conversation_id."""

    # Mock the model status to be enabled
    async def _mock_model_status():
        return True, False  # enabled, loading

    monkeypatch.setattr(web_api, "_llm_chat_model_status", _mock_model_status)
    monkeypatch.setattr(web_api, "_load_llm_chat_queue", lambda: [])
    monkeypatch.setattr(web_api, "_load_llm_chat_conversations", lambda: [])

    client = TestClient(web_api.app)
    res = client.post(
        "/api/llm_chat/send",
        json={
            "message": "Test",
            "conversationId": "550e8400-e29b-41d4-a716-446655440000",  # Valid UUID format but doesn't exist
        },
    )
    assert res.status_code == 404
    payload = res.json()
    assert "Conversation not found" in payload["detail"]


def test_llm_chat_conversation_validates_uuid_format() -> None:
    """Test /api/llm_chat/conversations/{id} validates UUID format."""
    client = TestClient(web_api.app)
    res = client.get("/api/llm_chat/conversations/not-a-uuid")
    assert res.status_code == 400
    payload = res.json()
    assert "Invalid conversation ID format" in payload["detail"]


def test_llm_chat_conversation_returns_404_for_missing(monkeypatch) -> None:
    """Test /api/llm_chat/conversations/{id} returns 404 for non-existent conversation."""
    monkeypatch.setattr(web_api, "_load_llm_chat_conversations", lambda: [])

    client = TestClient(web_api.app)
    valid_uuid = "550e8400-e29b-41d4-a716-446655440000"
    res = client.get(f"/api/llm_chat/conversations/{valid_uuid}")
    assert res.status_code == 404
    payload = res.json()
    assert "Conversation not found" in payload["detail"]


def test_llm_chat_conversation_returns_conversation_data(monkeypatch) -> None:
    """Test /api/llm_chat/conversations/{id} returns conversation with messages."""
    conv_id = "550e8400-e29b-41d4-a716-446655440000"
    mock_conversations = [
        {
            "id": conv_id,
            "title": "Test Chat",
            "created_at": "2025-01-01T10:00:00",
            "updated_at": "2025-01-01T10:05:00",
            "messages": [
                {
                    "role": "user",
                    "content": "Hello",
                    "created_at": "2025-01-01T10:00:00",
                },
                {
                    "role": "assistant",
                    "content": "Hi there!",
                    "created_at": "2025-01-01T10:00:05",
                },
            ],
        }
    ]

    monkeypatch.setattr(
        web_api, "_load_llm_chat_conversations", lambda: mock_conversations
    )

    client = TestClient(web_api.app)
    res = client.get(f"/api/llm_chat/conversations/{conv_id}")
    assert res.status_code == 200
    payload = res.json()

    # Verify conversation data
    assert payload["id"] == conv_id
    assert payload["title"] == "Test Chat"
    assert payload["createdAt"] == "2025-01-01T10:00:00"
    assert payload["updatedAt"] == "2025-01-01T10:05:00"
    assert len(payload["messages"]) == 2

    # Verify messages
    assert payload["messages"][0]["role"] == "user"
    assert payload["messages"][0]["content"] == "Hello"
    assert payload["messages"][0]["createdAt"] == "2025-01-01T10:00:00"

    assert payload["messages"][1]["role"] == "assistant"
    assert payload["messages"][1]["content"] == "Hi there!"
    assert payload["messages"][1]["createdAt"] == "2025-01-01T10:00:05"


def test_llm_chat_enable_returns_status(monkeypatch) -> None:
    """Test /api/llm_chat/enable returns model status."""

    # Mock start load to do nothing
    async def _mock_start_load():
        pass

    # Mock status to return loading state
    async def _mock_model_status():
        return False, True  # enabled, loading

    monkeypatch.setattr(web_api, "_start_llm_chat_model_load", _mock_start_load)
    monkeypatch.setattr(web_api, "_llm_chat_model_status", _mock_model_status)

    client = TestClient(web_api.app)
    res = client.post("/api/llm_chat/enable")
    assert res.status_code == 200
    payload = res.json()

    # Verify status structure
    assert "enabled" in payload
    assert "loading" in payload
    assert payload["enabled"] is False
    assert payload["loading"] is True


def test_llm_chat_send_starts_worker_when_loading(monkeypatch) -> None:
    """Test /api/llm_chat/send starts worker when model is loading."""

    # Mock the model status to be loading
    async def _mock_model_status():
        return False, True  # enabled=False, loading=True

    worker_started = []

    async def _mock_start_worker():
        worker_started.append(True)

    monkeypatch.setattr(web_api, "_llm_chat_model_status", _mock_model_status)
    monkeypatch.setattr(web_api, "_load_llm_chat_queue", lambda: [])
    monkeypatch.setattr(web_api, "_load_llm_chat_conversations", lambda: [])
    monkeypatch.setattr(web_api, "_save_llm_chat_queue", lambda x: None)
    monkeypatch.setattr(web_api, "_save_llm_chat_conversations", lambda x: None)
    monkeypatch.setattr(web_api, "_prune_queue", lambda q: q)
    monkeypatch.setattr(web_api, "_maybe_start_llm_chat_worker", _mock_start_worker)

    client = TestClient(web_api.app)
    res = client.post("/api/llm_chat/send", json={"message": "Test"})
    assert res.status_code == 200

    # Verify worker was started (fix for review comment about loading=True)
    assert len(worker_started) == 1


def test_build_chat_messages_filters_system_messages(monkeypatch) -> None:
    """Test _build_chat_messages filters system messages from conversation history."""
    # Set a system prompt
    monkeypatch.setattr(web_api, "_CHAT_SYSTEM_PROMPT", "System instructions")

    conversation = {
        "messages": [
            {"role": "system", "content": "Old system message"},
            {"role": "user", "content": "User message 1"},
            {"role": "assistant", "content": "Assistant response 1"},
            {"role": "user", "content": "User message 2"},
        ]
    }

    messages = web_api._build_chat_messages(conversation, "New user message")

    # Verify system prompt is at the start
    assert messages[0]["role"] == "system"
    assert messages[0]["content"] == "System instructions"

    # Verify old system message is filtered out
    system_count = sum(1 for msg in messages if msg["role"] == "system")
    assert system_count == 1

    # Verify other messages are included
    assert len(messages) == 5  # system + 2 user + 1 assistant + new user
    assert messages[1]["role"] == "user"
    assert messages[1]["content"] == "User message 1"
    assert messages[2]["role"] == "assistant"
    assert messages[3]["role"] == "user"
    assert messages[3]["content"] == "User message 2"
    assert messages[4]["role"] == "user"
    assert messages[4]["content"] == "New user message"


def test_llm_chat_queue_worker_saves_model_response(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv(str(EnvVar.CACHE_DIR), str(tmp_path))
    monkeypatch.setattr(web_api, "_LLM_CHAT_AGENT", None)
    monkeypatch.setattr(web_api, "_LLM_CHAT_WORKER_RUNNING", False)

    captured_messages: list[list[dict[str, str]]] = []

    class _FakeChatModel:
        def chat(self, messages):
            captured_messages.append(messages)
            return "worker-ok"

    async def _run_worker() -> None:
        monkeypatch.setattr(web_api, "_LLM_CHAT_MODEL", _FakeChatModel())
        now = web_api._now_iso()
        web_api._save_llm_chat_conversations(
            [
                {
                    "id": "550e8400-e29b-41d4-a716-446655440000",
                    "title": "Worker smoke",
                    "created_at": now,
                    "updated_at": now,
                    "messages": [],
                }
            ]
        )
        web_api._save_llm_chat_queue(
            [
                {
                    "id": "queue-1",
                    "conversation_id": "550e8400-e29b-41d4-a716-446655440000",
                    "content": "Reply with worker-ok",
                    "status": "queued",
                    "created_at": now,
                    "started_at": None,
                    "finished_at": None,
                    "error": None,
                }
            ]
        )

        await web_api._run_llm_chat_queue()

    asyncio.run(_run_worker())

    queue = web_api._load_llm_chat_queue()
    conversations = web_api._load_llm_chat_conversations()

    assert queue[0]["status"] == "done"
    assert queue[0]["error"] is None
    assert conversations[0]["messages"][-2:] == [
        {
            "role": "user",
            "content": "Reply with worker-ok",
            "created_at": conversations[0]["messages"][-2]["created_at"],
        },
        {
            "role": "assistant",
            "content": "worker-ok",
            "created_at": conversations[0]["messages"][-1]["created_at"],
        },
    ]
    assert captured_messages[0][-1] == {
        "role": web_api.MessageRole.USER.value,
        "content": "Reply with worker-ok",
    }


def test_llm_chat_queue_worker_builds_codex_inline(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv(str(EnvVar.CACHE_DIR), str(tmp_path))
    monkeypatch.setattr(web_api, "_LLM_CHAT_MODEL", None)
    monkeypatch.setattr(web_api, "_LLM_CHAT_MODEL_LOADING", False)
    monkeypatch.setattr(web_api, "_LLM_CHAT_AGENT", None)
    monkeypatch.setattr(web_api, "_LLM_CHAT_WORKER_RUNNING", False)

    captured_settings: list[dict[str, object]] = []

    class _FakeChatModel:
        def chat(self, messages):
            assert messages[-1]["content"] == "Reply with inline-ok"
            return "inline-ok"

    def _fake_build_model(settings, *, max_output_tokens: int):
        captured_settings.append(dict(settings))
        assert max_output_tokens == 256
        return _FakeChatModel()

    original_resolve_settings = getattr(web_api, "_resolve_llm_chat_settings")
    original_build_model = getattr(web_api, "_build_llm_from_settings")
    setattr(
        web_api,
        "_resolve_llm_chat_settings",
        lambda: {
            "backend": "codex",
            "device": "cpu",
            "codex": {"model": "gpt-5.5", "modelOptions": []},
            "triton": {},
        },
    )
    setattr(web_api, "_build_llm_from_settings", _fake_build_model)
    web_api._llm_chat_component._sync_api_globals()
    monkeypatch.setattr(web_api, "_build_llm_chat_agent_sync", lambda _model: None)

    async def _run_worker() -> None:
        now = web_api._now_iso()
        web_api._save_llm_chat_conversations(
            [
                {
                    "id": "550e8400-e29b-41d4-a716-446655440000",
                    "title": "Inline worker smoke",
                    "created_at": now,
                    "updated_at": now,
                    "messages": [],
                }
            ]
        )
        web_api._save_llm_chat_queue(
            [
                {
                    "id": "queue-inline",
                    "conversation_id": "550e8400-e29b-41d4-a716-446655440000",
                    "content": "Reply with inline-ok",
                    "status": "queued",
                    "created_at": now,
                    "started_at": None,
                    "finished_at": None,
                    "error": None,
                }
            ]
        )

        monkeypatch.setattr(web_api, "_LLM_CHAT_MODEL", None)
        monkeypatch.setattr(web_api, "_LLM_CHAT_MODEL_LOADING", False)
        await web_api._run_llm_chat_queue()

    try:
        asyncio.run(_run_worker())
    finally:
        setattr(web_api, "_resolve_llm_chat_settings", original_resolve_settings)
        setattr(web_api, "_build_llm_from_settings", original_build_model)
        web_api._llm_chat_component._sync_api_globals()

    queue = web_api._load_llm_chat_queue()
    conversations = web_api._load_llm_chat_conversations()

    assert captured_settings[0]["backend"] == "codex"
    assert web_api._LLM_CHAT_MODEL is not None
    assert web_api._LLM_CHAT_MODEL_LOADING is False
    assert queue[0]["status"] == "done"
    assert queue[0]["error"] is None
    assert conversations[0]["messages"][-1]["content"] == "inline-ok"


def test_llm_chat_queue_worker_marks_inline_codex_load_failure(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.setenv(str(EnvVar.CACHE_DIR), str(tmp_path))
    monkeypatch.setattr(web_api, "_LLM_CHAT_MODEL", None)
    monkeypatch.setattr(web_api, "_LLM_CHAT_MODEL_LOADING", False)
    monkeypatch.setattr(web_api, "_LLM_CHAT_AGENT", None)
    monkeypatch.setattr(web_api, "_LLM_CHAT_WORKER_RUNNING", False)

    def _fake_build_model(_settings, *, max_output_tokens: int):
        assert max_output_tokens == 256
        raise ValueError("codex unavailable")

    original_resolve_settings = getattr(web_api, "_resolve_llm_chat_settings")
    original_build_model = getattr(web_api, "_build_llm_from_settings")
    setattr(
        web_api,
        "_resolve_llm_chat_settings",
        lambda: {
            "backend": "codex",
            "device": "cpu",
            "codex": {"model": "gpt-5.5", "modelOptions": []},
            "triton": {},
        },
    )
    setattr(web_api, "_build_llm_from_settings", _fake_build_model)
    web_api._llm_chat_component._sync_api_globals()

    async def _run_worker() -> None:
        now = web_api._now_iso()
        web_api._save_llm_chat_conversations(
            [
                {
                    "id": "550e8400-e29b-41d4-a716-446655440000",
                    "title": "Inline failure smoke",
                    "created_at": now,
                    "updated_at": now,
                    "messages": [],
                }
            ]
        )
        web_api._save_llm_chat_queue(
            [
                {
                    "id": "queue-inline-fail",
                    "conversation_id": "550e8400-e29b-41d4-a716-446655440000",
                    "content": "This should fail",
                    "status": "queued",
                    "created_at": now,
                    "started_at": None,
                    "finished_at": None,
                    "error": None,
                }
            ]
        )

        await web_api._run_llm_chat_queue()

    try:
        asyncio.run(_run_worker())
    finally:
        setattr(web_api, "_resolve_llm_chat_settings", original_resolve_settings)
        setattr(web_api, "_build_llm_from_settings", original_build_model)
        web_api._llm_chat_component._sync_api_globals()

    queue = web_api._load_llm_chat_queue()
    conversations = web_api._load_llm_chat_conversations()

    assert queue[0]["status"] == "failed"
    assert queue[0]["finished_at"]
    assert queue[0]["error"] == "ValueError: codex unavailable"
    assert conversations[0]["messages"] == []
