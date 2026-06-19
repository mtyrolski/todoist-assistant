"""Tests for FastAPI LLM chat endpoints."""

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
    assert "usage" in payload
    assert "conversations" in payload

    # Verify Codex-only idle state
    assert payload["enabled"] is False
    assert payload["loading"] is False
    assert payload["backend"]["selected"] == "codex"
    assert payload["backend"]["codex"]["model"] == "gpt-5.5"
    assert payload["model"]["selected"] == "gpt-5.5"
    assert payload["device"]["selected"] == "cpu"
    assert payload["usage"]["totals"]["inferenceCount"] == 0
    assert payload["usage"]["current"]["modelId"] == "gpt-5.5"
    assert payload["assistant"]["mode"] == "codex"
    assert payload["assistant"]["telemetry"]["enabled"] is False
    assert payload["statistics"] == {
        "conversationCount": 0,
        "messageCount": 0,
        "userMessageCount": 0,
        "assistantMessageCount": 0,
        "toolMessageCount": 0,
    }
    assert payload["conversations"] == []


def test_dashboard_llm_chat_reports_invalid_backend_as_json(
    monkeypatch, tmp_path
) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text("TODOIST_AGENT_BACKEND='unsupported'", encoding="utf-8")
    monkeypatch.delenv(str(web_api.EnvVar.AGENT_BACKEND), raising=False)
    monkeypatch.setattr(web_api, "_resolve_env_path", lambda: env_path)

    client = TestClient(web_api.app)
    res = client.get("/api/dashboard/llm_chat")

    assert res.status_code == 409
    assert res.json() == {"detail": "Unsupported LLM backend: unsupported"}


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


def test_llm_chat_settings_response_exposes_codex_options(
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

    client = TestClient(web_api.app)
    res = client.get("/api/llm_chat/settings")

    assert res.status_code == 200
    payload = res.json()
    assert payload["envPath"] == ".env"
    assert payload["codex"]["model"] == "gpt-5.5"
    assert "gpt-5.5" in {option["id"] for option in payload["codex"]["modelOptions"]}


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


def test_llm_chat_update_settings_rejects_unknown_backend(monkeypatch) -> None:
    monkeypatch.setattr(web_api, "_available_llm_chat_devices", lambda: ["cpu", "cuda"])

    client = TestClient(web_api.app)
    res = client.put(
        "/api/llm_chat/settings",
        json={
            "backend": "unknown",
            "device": "cpu",
        },
    )

    assert res.status_code == 400
    assert res.json()["detail"] == "Unsupported LLM backend."


def test_llm_chat_update_settings_rejects_disabled_backend(
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
            "backend": "disabled",
            "device": "cpu",
        },
    )

    assert res.status_code == 400
    assert res.json()["detail"] == "Unsupported LLM backend."


def test_llm_chat_send_requires_message() -> None:
    """Test /api/llm_chat/send validates message is required."""
    client = TestClient(web_api.app)
    res = client.post("/api/llm_chat/send", json={})
    assert res.status_code == 400
    payload = res.json()
    assert "message is required" in payload["detail"]


def test_llm_chat_send_creates_new_conversation(monkeypatch) -> None:
    """Test /api/llm_chat/send runs a direct turn for a new conversation."""

    saved_conversations = []

    def _mock_save_conversations(items):
        saved_conversations.clear()
        saved_conversations.extend(items)

    async def _mock_turn(conversation, message):
        assert conversation["messages"] == []
        return [
            {"role": web_api.MessageRole.USER.value, "content": message},
            {"role": web_api.MessageRole.ASSISTANT.value, "content": "assistant-ok"},
        ]

    monkeypatch.setattr(web_api, "_load_llm_chat_conversations", lambda: [])
    monkeypatch.setattr(
        web_api, "_save_llm_chat_conversations", _mock_save_conversations
    )
    monkeypatch.setattr(web_api, "_run_llm_chat_turn", _mock_turn)

    client = TestClient(web_api.app)
    res = client.post("/api/llm_chat/send", json={"message": "Hello, world!"})
    assert res.status_code == 200
    payload = res.json()

    assert "conversationId" in payload
    assert payload["conversation"]["messages"][0]["content"] == "Hello, world!"
    assert payload["conversation"]["messages"][1]["content"] == "assistant-ok"

    assert len(saved_conversations) == 1
    conv = saved_conversations[0]
    assert conv["title"] == "Hello, world!"
    assert conv["id"] == payload["conversationId"]
    assert "created_at" in conv
    assert "updated_at" in conv
    assert [msg["content"] for msg in conv["messages"]] == [
        "Hello, world!",
        "assistant-ok",
    ]


def test_llm_chat_send_uses_existing_conversation(monkeypatch) -> None:
    """Test /api/llm_chat/send appends to an existing conversation directly."""

    existing_conv_id = "550e8400-e29b-41d4-a716-446655440000"
    existing_conversations = [
        {
            "id": existing_conv_id,
            "title": "Existing Chat",
            "created_at": "2025-01-01T10:00:00",
            "updated_at": "2025-01-01T10:00:00",
            "messages": [
                {
                    "role": "user",
                    "content": "Earlier",
                    "created_at": "2025-01-01T10:00:00",
                }
            ],
        }
    ]

    saved_conversations = []

    def _mock_save_conversations(items):
        saved_conversations.clear()
        saved_conversations.extend(items)

    async def _mock_turn(conversation, message):
        assert conversation["id"] == existing_conv_id
        return [
            {"role": web_api.MessageRole.USER.value, "content": message},
            {"role": web_api.MessageRole.ASSISTANT.value, "content": "follow-up-ok"},
        ]

    monkeypatch.setattr(
        web_api, "_load_llm_chat_conversations", lambda: existing_conversations[:]
    )
    monkeypatch.setattr(
        web_api, "_save_llm_chat_conversations", _mock_save_conversations
    )
    monkeypatch.setattr(web_api, "_run_llm_chat_turn", _mock_turn)

    client = TestClient(web_api.app)
    res = client.post(
        "/api/llm_chat/send",
        json={"message": "Follow up", "conversationId": existing_conv_id},
    )
    assert res.status_code == 200
    payload = res.json()

    assert payload["conversationId"] == existing_conv_id
    assert len(saved_conversations) == 1
    assert saved_conversations[0]["id"] == existing_conv_id
    assert saved_conversations[0]["title"] == "Existing Chat"
    assert [msg["content"] for msg in saved_conversations[0]["messages"]] == [
        "Earlier",
        "Follow up",
        "follow-up-ok",
    ]


def test_llm_chat_send_handles_task_proposals_from_pasted_content(
    monkeypatch,
) -> None:
    saved_conversations = []

    def _mock_save_conversations(items):
        saved_conversations.clear()
        saved_conversations.extend(items)

    async def _mock_turn(_conversation, _message):
        return [
            {
                "role": web_api.MessageRole.USER.value,
                "content": "notes: ship chat, simplify old flow",
            },
            {
                "role": web_api.MessageRole.ASSISTANT.value,
                "content": "Proposed tasks:\n- Ship direct chat\n- Remove old staging UI\nNo tasks created.",
            },
        ]

    monkeypatch.setattr(web_api, "_load_llm_chat_conversations", lambda: [])
    monkeypatch.setattr(
        web_api, "_save_llm_chat_conversations", _mock_save_conversations
    )
    monkeypatch.setattr(web_api, "_run_llm_chat_turn", _mock_turn)

    client = TestClient(web_api.app)
    res = client.post(
        "/api/llm_chat/send",
        json={"message": "notes: ship chat, simplify old flow"},
    )

    assert res.status_code == 200
    assistant_message = res.json()["conversation"]["messages"][-1]["content"]
    assert "Proposed tasks:" in assistant_message
    assert "No tasks created." in assistant_message
    assert saved_conversations[0]["messages"][-1]["content"] == assistant_message


def test_llm_chat_send_handles_status_update_questions(monkeypatch) -> None:
    async def _mock_turn(_conversation, message):
        return [
            {"role": web_api.MessageRole.USER.value, "content": message},
            {
                "role": web_api.MessageRole.ASSISTANT.value,
                "content": "Status update: direct chat is running and the old staging UI is gone.",
            },
        ]

    saved_conversations = []

    def _mock_save_conversations(items):
        saved_conversations.clear()
        saved_conversations.extend(items)

    monkeypatch.setattr(web_api, "_load_llm_chat_conversations", lambda: [])
    monkeypatch.setattr(
        web_api, "_save_llm_chat_conversations", _mock_save_conversations
    )
    monkeypatch.setattr(web_api, "_run_llm_chat_turn", _mock_turn)

    client = TestClient(web_api.app)
    res = client.post("/api/llm_chat/send", json={"message": "status update?"})

    assert res.status_code == 200
    assert "Status update:" in res.json()["conversation"]["messages"][-1]["content"]


def test_llm_chat_send_preserves_operation_events(monkeypatch) -> None:
    saved_conversations = []

    def _mock_save_conversations(items):
        saved_conversations.clear()
        saved_conversations.extend(items)

    async def _mock_turn(_conversation, _message):
        return [
            {
                "role": web_api.MessageRole.USER.value,
                "content": "check scripts",
            },
            {
                "role": "operation",
                "content": "Calling python_repl with code:\n```python\nscript_catalog()\n```",
            },
            {
                "role": "tool",
                "content": "python_repl output:\n[{'name': 'status'}]",
            },
            {
                "role": web_api.MessageRole.ASSISTANT.value,
                "content": "The status script is available.",
            },
        ]

    monkeypatch.setattr(web_api, "_load_llm_chat_conversations", lambda: [])
    monkeypatch.setattr(
        web_api, "_save_llm_chat_conversations", _mock_save_conversations
    )
    monkeypatch.setattr(web_api, "_run_llm_chat_turn", _mock_turn)

    client = TestClient(web_api.app)
    res = client.post("/api/llm_chat/send", json={"message": "check scripts"})

    assert res.status_code == 200
    roles = [msg["role"] for msg in res.json()["conversation"]["messages"]]
    assert roles == ["user", "operation", "tool", "assistant"]
    assert [msg["role"] for msg in saved_conversations[0]["messages"]] == roles


def test_llm_chat_send_rejects_invalid_conversation_id(monkeypatch) -> None:
    """Test /api/llm_chat/send returns 404 for non-existent conversation_id."""

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


def test_llm_chat_conversation_can_be_renamed(monkeypatch) -> None:
    conv_id = "550e8400-e29b-41d4-a716-446655440000"
    conversations = [
        {
            "id": conv_id,
            "title": "Old title",
            "created_at": "2025-01-01T10:00:00",
            "updated_at": "2025-01-01T10:00:00",
            "messages": [],
        }
    ]
    saved: list[dict[str, object]] = []
    monkeypatch.setattr(web_api, "_load_llm_chat_conversations", lambda: conversations)
    monkeypatch.setattr(
        web_api,
        "_save_llm_chat_conversations",
        lambda items: saved.extend(items),
    )

    client = TestClient(web_api.app)
    res = client.patch(
        f"/api/llm_chat/conversations/{conv_id}", json={"title": "Weekly review"}
    )

    assert res.status_code == 200
    assert res.json()["title"] == "Weekly review"
    assert saved[0]["title"] == "Weekly review"


def test_llm_chat_conversation_can_be_deleted(monkeypatch) -> None:
    conv_id = "550e8400-e29b-41d4-a716-446655440000"
    conversations = [{"id": conv_id, "title": "Delete me", "messages": []}]
    saved: list[list[dict[str, object]]] = []
    monkeypatch.setattr(web_api, "_load_llm_chat_conversations", lambda: conversations)
    monkeypatch.setattr(
        web_api,
        "_save_llm_chat_conversations",
        lambda items: saved.append(items),
    )

    client = TestClient(web_api.app)
    res = client.delete(f"/api/llm_chat/conversations/{conv_id}")

    assert res.status_code == 200
    assert res.json() == {"deleted": True, "conversationId": conv_id}
    assert saved == [[]]


def test_llm_chat_enable_returns_status(monkeypatch) -> None:
    """Test /api/llm_chat/enable returns model status."""
    monkeypatch.setenv(str(EnvVar.AGENT_BACKEND), "codex")
    monkeypatch.setenv(str(EnvVar.AGENT_CODEX_MODEL), "gpt-5.5")

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
