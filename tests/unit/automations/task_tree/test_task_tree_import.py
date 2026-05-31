
import pytest

from todoist.task_tree_import import (
    create_task_tree,
    normalize_task_tree_payload,
    render_task_tree_plan,
)


class FakeTaskDb:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def insert_task(self, **payload: object) -> dict[str, object]:
        self.calls.append(payload)
        return {"id": f"task-{len(self.calls)}"}


def test_normalize_task_tree_payload_accepts_camel_case_fields() -> None:
    payload = normalize_task_tree_payload(
        {
            "projectId": "project-1",
            "labels": ["@ai-import"],
            "tasks": [
                {
                    "content": "Plan release",
                    "dueString": "next Monday",
                    "children": [{"content": "Draft notes"}],
                }
            ],
        }
    )

    assert payload.project_id == "project-1"
    assert payload.labels == ["ai-import"]
    assert payload.tasks[0].due_string == "next Monday"
    assert payload.tasks[0].children[0].content == "Draft notes"


def test_render_task_tree_plan_includes_nested_numbering_and_inherited_labels() -> None:
    payload = normalize_task_tree_payload(
        {
            "projectId": "project-1",
            "labels": ["ai-import"],
            "tasks": [
                {
                    "content": "Plan release",
                    "labels": ["planning"],
                    "children": [{"content": "Draft notes"}],
                }
            ],
        }
    )

    assert render_task_tree_plan(payload).splitlines() == [
        "1. Plan release labels=['ai-import', 'planning']",
        "1.1. Draft notes labels=['ai-import', 'planning']",
    ]


def test_create_task_tree_creates_children_under_created_parent() -> None:
    payload = normalize_task_tree_payload(
        {
            "projectId": "project-1",
            "labels": ["ai-import"],
            "tasks": [
                {
                    "content": "Plan release",
                    "labels": ["planning"],
                    "children": [{"content": "Draft notes", "labels": ["writing"]}],
                }
            ],
        }
    )
    db = FakeTaskDb()

    created = create_task_tree(payload, db=db, dry_run=False)  # type: ignore[arg-type]

    assert created == [
        {"id": "task-1", "content": "Plan release", "parentId": None, "projectId": "project-1"},
        {"id": "task-2", "content": "Draft notes", "parentId": "task-1", "projectId": "project-1"},
    ]
    assert db.calls == [
        {
            "content": "Plan release",
            "labels": ["ai-import", "planning"],
            "project_id": "project-1",
        },
        {
            "content": "Draft notes",
            "labels": ["ai-import", "planning", "writing"],
            "parent_id": "task-1",
        },
    ]


def test_create_task_tree_dry_run_does_not_write() -> None:
    payload = normalize_task_tree_payload(
        {"projectId": "project-1", "tasks": [{"content": "Plan release"}]}
    )
    db = FakeTaskDb()

    assert create_task_tree(payload, db=db, dry_run=True) == []  # type: ignore[arg-type]
    assert db.calls == []


def test_create_task_tree_requires_project_for_top_level_tasks() -> None:
    payload = normalize_task_tree_payload([{"content": "Plan release"}])

    with pytest.raises(ValueError, match="projectId is required"):
        create_task_tree(payload, db=FakeTaskDb(), dry_run=False)  # type: ignore[arg-type]
