import pytest

from tests.factories import make_project, make_task
from todoist.features.ai_context import (
    AI_CONTEXT_LABEL,
    AI_CONTEXT_UPDATE_COMMENT_HEADER,
    MAX_AI_CONTEXT_DESCRIPTION_CHARS,
    aggregate_ai_context,
    collect_ai_context,
    is_ai_context_task,
    is_non_removable_content,
    merge_context_description,
    protected_context_content,
    render_ai_context,
    upsert_ai_context_task,
)


class _FakeDb:
    def __init__(self) -> None:
        self.created = []
        self.updated = []
        self.comments = []

    def insert_task(self, **kwargs):
        self.created.append(kwargs)
        return {"id": "context-new"}

    def update_task(self, task_id, **kwargs):
        self.updated.append((task_id, kwargs))
        return {"id": task_id}

    def create_comment(self, *, task_id, content):
        self.comments.append({"task_id": task_id, "content": content})
        return {"id": f"comment-{len(self.comments)}"}


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
    rendered = render_ai_context(entries)
    assert "Project: Platform (1 context task(s))" in rendered
    assert "HIGH-PRIORITY project AI context" in rendered
    assert "explicit current user directions take precedence" in rendered
    assert "- * Architecture: Prefer event-driven boundaries." in rendered
    assert entries[0].updated_at == "2024-01-01T00:00:00Z"


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
        description="Explain the updated fact completely.",
        existing_entries=entries,
    )

    assert protected_context_content("**  New durable fact") == "* New durable fact"
    assert created["content"] == "* New durable fact"
    assert db.created[0]["labels"] == [AI_CONTEXT_LABEL]
    assert updated["action"] == "updated"
    assert updated["content"] == "* Updated durable fact"
    assert db.updated[0][1] == {
        "content": "* Updated durable fact",
        "description": "Explain the updated fact completely.",
    }
    assert len(db.comments) == 1
    assert db.comments[0]["task_id"] == "context-1"
    assert AI_CONTEXT_UPDATE_COMMENT_HEADER in db.comments[0]["content"]
    assert "Title — from:\n* Existing" in db.comments[0]["content"]
    assert "Title — to:\n* Updated durable fact" in db.comments[0]["content"]
    assert "Description — from:\n(empty)" in db.comments[0]["content"]
    assert (
        "Description — to:\nExplain the updated fact completely."
        in db.comments[0]["content"]
    )
    assert created["auditComment"] is None


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

    assert result["action"] == "unchanged"
    assert result["taskId"] == "context-1"
    assert db.created == []
    assert db.updated == []
    assert db.comments == []


def test_ai_context_updates_accumulate_without_losing_existing_facts() -> None:
    project = make_project(
        project_id="project-1",
        tasks=[
            make_task(
                "context-1",
                content="* Release policy",
                description="Run unit tests before release.",
                labels=[AI_CONTEXT_LABEL],
                project_id="project-1",
            )
        ],
    )
    db = _FakeDb()

    result = upsert_ai_context_task(
        db,
        project_id="project-1",
        task_id="context-1",
        content="Release policy",
        description="Run a staging smoke test before production.",
        existing_entries=collect_ai_context([project]),
    )

    assert result["content"] == "* Release policy"
    assert result["description"] == (
        "Run unit tests before release.\nRun a staging smoke test before production."
    )
    assert db.updated[0][1] == {"description": result["description"]}
    assert len(db.comments) == 1
    audit = db.comments[0]["content"]
    assert "Description — from:\nRun unit tests before release." in audit
    assert f"Description — to:\n{result['description']}" in audit


def test_ai_context_creation_requires_description_and_does_not_comment() -> None:
    db = _FakeDb()

    with pytest.raises(ValueError, match="description is required"):
        upsert_ai_context_task(
            db,
            project_id="project-1",
            content="Release policy",
        )

    assert db.created == []
    assert db.comments == []


def test_ai_context_cannot_update_an_unexplained_task_without_description() -> None:
    project = make_project(
        project_id="project-1",
        tasks=[
            make_task(
                "context-1",
                content="* Legacy topic",
                labels=[AI_CONTEXT_LABEL],
                project_id="project-1",
            )
        ],
    )
    db = _FakeDb()

    with pytest.raises(ValueError, match="make the resulting task self-contained"):
        upsert_ai_context_task(
            db,
            project_id="project-1",
            task_id="context-1",
            content="Updated topic",
            existing_entries=collect_ai_context([project]),
        )

    assert db.updated == []
    assert db.comments == []


def test_context_merge_keeps_more_complete_text_and_rejects_lossy_overflow() -> None:
    existing = "Production deploys require approval and a rollback plan."

    assert merge_context_description(existing, "approval and a rollback") == existing
    assert (
        merge_context_description(existing, f"Policy: {existing}")
        == f"Policy: {existing}"
    )
    with pytest.raises(ValueError, match="separate ai_context task"):
        merge_context_description(
            "x" * (MAX_AI_CONTEXT_DESCRIPTION_CHARS - 1), "new fact"
        )


def test_ai_context_rejects_update_when_exact_audit_would_be_too_large() -> None:
    project = make_project(
        project_id="project-1",
        tasks=[
            make_task(
                "context-1",
                content="* Large context",
                description="x" * 7_000,
                labels=[AI_CONTEXT_LABEL],
                project_id="project-1",
            )
        ],
    )
    db = _FakeDb()

    with pytest.raises(ValueError, match="exact from/to values"):
        upsert_ai_context_task(
            db,
            project_id="project-1",
            task_id="context-1",
            content="Large context",
            description="new fact",
            existing_entries=collect_ai_context([project]),
        )

    assert db.updated == []
    assert db.comments == []


def test_dynamic_aggregation_keeps_multiple_topics_and_projects() -> None:
    projects = [
        make_project(
            project_id="project-1",
            name="Platform",
            tasks=[
                make_task(
                    "context-architecture",
                    content="* Architecture",
                    labels=[AI_CONTEXT_LABEL],
                    project_id="project-1",
                ),
                make_task(
                    "context-release",
                    content="* Release policy",
                    labels=[AI_CONTEXT_LABEL],
                    project_id="project-1",
                ),
            ],
        ),
        make_project(
            project_id="project-2",
            name="Research",
            tasks=[
                make_task(
                    "context-data",
                    content="* Data source",
                    labels=[AI_CONTEXT_LABEL],
                    project_id="project-2",
                )
            ],
        ),
    ]

    aggregates = aggregate_ai_context(collect_ai_context(projects))

    assert [(item.project_name, len(item.entries)) for item in aggregates] == [
        ("Platform", 2),
        ("Research", 1),
    ]
    assert aggregates[0].as_dict()["contextCount"] == 2


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
