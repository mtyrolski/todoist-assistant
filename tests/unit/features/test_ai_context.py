from tests.factories import make_project, make_task
from todoist.features.ai_context import (
    AI_CONTEXT_LABEL,
    collect_ai_context,
    is_ai_context_task,
    is_non_removable_content,
    protected_context_content,
    render_ai_context,
    upsert_ai_context_task,
)


class _FakeDb:
    def __init__(self) -> None:
        self.created = []
        self.updated = []

    def insert_task(self, **kwargs):
        self.created.append(kwargs)
        return {"id": "context-new"}

    def update_task(self, task_id, **kwargs):
        self.updated.append((task_id, kwargs))
        return {"id": task_id}


def test_collect_ai_context_requires_label_and_literal_prefix() -> None:
    valid = make_task(
        "valid",
        content="* Architecture",
        description="Prefer event-driven boundaries.",
        labels=[AI_CONTEXT_LABEL],
        project_id="project-1",
    )
    missing_label = make_task("missing-label", content="* Private note", labels=[])
    missing_prefix = make_task(
        "missing-prefix", content="Ordinary task", labels=[AI_CONTEXT_LABEL]
    )
    project = make_project(
        project_id="project-1",
        name="Platform",
        tasks=[valid, missing_label, missing_prefix],
    )

    entries = collect_ai_context([project])

    assert is_ai_context_task(valid) is True
    assert is_non_removable_content("* protected") is True
    assert is_non_removable_content("*missing-space") is False
    assert [entry.task_id for entry in entries] == ["valid"]
    assert (
        "[Platform] * Architecture: Prefer event-driven boundaries."
        in render_ai_context(entries)
    )


def test_upsert_ai_context_is_constrained_to_context_tasks_in_project() -> None:
    project = make_project(
        project_id="project-1",
        tasks=[
            make_task(
                "context-1",
                content="* Existing",
                labels=[AI_CONTEXT_LABEL],
                project_id="project-1",
            )
        ],
    )
    entries = collect_ai_context([project])
    db = _FakeDb()

    created = upsert_ai_context_task(
        db,
        project_id="project-1",
        content="New durable fact",
        description="Reusable detail",
        existing_entries=entries,
    )
    updated = upsert_ai_context_task(
        db,
        project_id="project-1",
        task_id="context-1",
        content="* Updated durable fact",
        existing_entries=entries,
    )

    assert protected_context_content("**  New durable fact") == "* New durable fact"
    assert created["content"] == "* New durable fact"
    assert db.created[0]["labels"] == [AI_CONTEXT_LABEL]
    assert updated["action"] == "updated"
    assert db.updated[0][1]["content"] == "* Updated durable fact"
    assert "description" not in db.updated[0][1]


def test_upsert_ai_context_updates_exact_title_instead_of_duplicating() -> None:
    project = make_project(
        project_id="project-1",
        tasks=[
            make_task(
                "context-1",
                content="* Existing durable fact",
                description="Original detail",
                labels=[AI_CONTEXT_LABEL],
                project_id="project-1",
            )
        ],
    )
    db = _FakeDb()

    result = upsert_ai_context_task(
        db,
        project_id="project-1",
        content="Existing durable fact",
        existing_entries=collect_ai_context([project]),
    )

    assert result["action"] == "updated"
    assert result["taskId"] == "context-1"
    assert db.created == []
    assert db.updated[0][1]["description"] == "Original detail"


def test_upsert_ai_context_rejects_cross_project_or_ordinary_task_id() -> None:
    db = _FakeDb()

    try:
        upsert_ai_context_task(
            db,
            project_id="project-1",
            task_id="ordinary-task",
            content="Should not update",
            existing_entries=[],
        )
    except ValueError as exc:
        assert "existing ai_context task in this project" in str(exc)
    else:
        raise AssertionError("Expected constrained update to fail")

    assert db.updated == []
