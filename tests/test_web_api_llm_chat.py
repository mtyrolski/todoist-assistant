"""Tests for FastAPI LLM chat endpoints."""

from fastapi.testclient import TestClient

import todoist.web.api as web_api

# pylint: disable=protected-access


# LLM Chat endpoint tests


def test_dashboard_llm_chat_returns_structure(monkeypatch, tmp_path) -> None:
    """Test /api/dashboard/llm_chat returns expected structure when model not loaded."""
    monkeypatch.delenv("OPEN_AI_SECRET_KEY", raising=False)
    monkeypatch.delenv("OPEN_AI_KEY_NAME", raising=False)
    monkeypatch.delenv("OPEN_AI_MODEL", raising=False)
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
    assert payload["backend"]["selected"] == "transformers_local"
    assert payload["backend"]["triton"]["configured"] is True
    assert payload["backend"]["triton"]["modelId"] in {
        option["id"] for option in payload["backend"]["triton"]["modelOptions"]
    }
    assert payload["model"]["selected"] == "mistralai/Ministral-3-3B-Instruct-2512"
    assert payload["device"]["selected"] == "cpu"
    assert payload["usage"]["totals"]["inferenceCount"] == 0
    assert payload["usage"]["current"]["modelId"] == "mistralai/Ministral-3-3B-Instruct-2512"
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
            "backend": "transformers_local",
            "device": "cuda",
            "localModelId": "Qwen/Qwen2.5-1.5B-Instruct",
        },
    )

    assert res.status_code == 200
    payload = res.json()
    assert payload["backend"] == "transformers_local"
    assert payload["device"] == "cuda"
    assert payload["localModelId"] == "Qwen/Qwen2.5-1.5B-Instruct"
    assert payload["reloadedRequired"] is True
    assert env_path.read_text(encoding="utf-8").find("TODOIST_AGENT_DEVICE='cuda'") >= 0
    assert env_path.read_text(encoding="utf-8").find("TODOIST_AGENT_MODEL_ID='Qwen/Qwen2.5-1.5B-Instruct'") >= 0
    assert web_api._LLM_CHAT_MODEL is None
    assert web_api._LLM_CHAT_AGENT is None

def test_llm_chat_settings_response_does_not_expose_secret_key(
    monkeypatch, tmp_path
) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text(
        "\n".join(
            [
                "OPEN_AI_SECRET_KEY='sk-test'",
                "OPEN_AI_KEY_NAME='primary-key'",
                "OPEN_AI_MODEL='gpt-5-mini'",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("OPEN_AI_SECRET_KEY", "sk-test")
    monkeypatch.setenv("OPEN_AI_KEY_NAME", "primary-key")
    monkeypatch.setenv("OPEN_AI_MODEL", "gpt-5-mini")
    monkeypatch.setattr(web_api, "_resolve_env_path", lambda: env_path)
    monkeypatch.setattr(web_api, "_available_llm_chat_devices", lambda: ["cpu", "cuda"])
    monkeypatch.setattr(web_api, "_triton_ready", lambda _settings: True)

    client = TestClient(web_api.app)
    res = client.get("/api/llm_chat/settings")

    assert res.status_code == 200
    payload = res.json()
    assert payload["openai"]["configured"] is True
    assert payload["openai"]["keyName"] == "primary-key"
    assert payload["openai"]["model"] == "gpt-5-mini"
    assert "secretKey" not in payload["openai"]
    assert payload["envPath"] == ".env"
    assert "mistralai/Mistral-Nemo-Instruct-2407" in {
        option["id"] for option in payload["localModelOptions"]
    }
    assert "mistralai/Mistral-Nemo-Instruct-2407" in {
        option["id"] for option in payload["triton"]["modelOptions"]
    }
    assert "gpt-5-nano" in {option["id"] for option in payload["openai"]["modelOptions"]}

def test_llm_chat_update_settings_rejects_unavailable_device(monkeypatch) -> None:
    monkeypatch.setattr(web_api, "_available_llm_chat_devices", lambda: ["cpu"])

    client = TestClient(web_api.app)
    res = client.put(
        "/api/llm_chat/settings",
        json={"backend": "transformers_local", "device": "cuda"},
    )

    assert res.status_code == 400

def test_llm_chat_update_settings_supports_openai_backend(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.setenv("OPEN_AI_SECRET_KEY", "sk-test")
    monkeypatch.setenv("OPEN_AI_KEY_NAME", "primary-key")
    monkeypatch.setenv("OPEN_AI_MODEL", "gpt-5-mini")
    env_path = tmp_path / ".env"
    env_path.write_text(
        "\n".join(
            [
                "OPEN_AI_SECRET_KEY='sk-test'",
                "OPEN_AI_KEY_NAME='primary-key'",
                "OPEN_AI_MODEL='gpt-5-mini'",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(web_api, "_resolve_env_path", lambda: env_path)
    monkeypatch.setattr(web_api, "_available_llm_chat_devices", lambda: ["cpu", "cuda"])
    monkeypatch.setattr(web_api, "_LLM_CHAT_MODEL", object())
    monkeypatch.setattr(web_api, "_LLM_CHAT_AGENT", object())
    monkeypatch.setattr(web_api, "_LLM_CHAT_MODEL_LOADING", False)

    client = TestClient(web_api.app)
    res = client.put(
        "/api/llm_chat/settings",
        json={"backend": "openai", "device": "cpu"},
    )

    assert res.status_code == 200
    payload = res.json()
    assert payload["backend"] == "openai"
    assert payload["openai"]["configured"] is True
    assert payload["openai"]["keyName"] == "primary-key"
    assert payload["openai"]["model"] == "gpt-5-mini"
    assert "secretKey" not in payload["openai"]
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
            "tritonModelId": "Qwen/Qwen2.5-1.5B-Instruct",
        },
    )

    assert res.status_code == 200
    payload = res.json()
    assert payload["backend"] == "triton_local"
    assert payload["triton"]["healthy"] is True
    assert payload["triton"]["modelName"] == "todoist_llm"
    assert payload["triton"]["modelId"] == "Qwen/Qwen2.5-1.5B-Instruct"
    saved = env_path.read_text(encoding="utf-8")
    assert "TODOIST_AGENT_BACKEND='triton_local'" in saved
    assert "TODOIST_AGENT_TRITON_MODEL_ID='Qwen/Qwen2.5-1.5B-Instruct'" in saved

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
