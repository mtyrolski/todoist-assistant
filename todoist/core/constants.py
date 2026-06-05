"""Centralized Todoist constant definitions."""

from enum import StrEnum


class TaskField(StrEnum):
    CONTENT = "content"
    DESCRIPTION = "description"
    PROJECT_ID = "project_id"
    SECTION_ID = "section_id"
    PARENT_ID = "parent_id"
    ORDER = "order"
    LABELS = "labels"
    PRIORITY = "priority"
    DUE_STRING = "due_string"
    DUE_DATE = "due_date"
    DUE_DATETIME = "due_datetime"
    DUE_LANG = "due_lang"
    ASSIGNEE_ID = "assignee_id"
    DURATION = "duration"
    DURATION_UNIT = "duration_unit"
    DEADLINE_DATE = "deadline_date"
    DEADLINE_LANG = "deadline_lang"
    NAME = "name"
    ID = "id"


class EventExtraField(StrEnum):
    CONTENT = "content"
    NAME = "name"
    DUE_DATE = "due_date"
    LAST_DUE_DATE = "last_due_date"


class EventType(StrEnum):
    ADDED = "added"
    UPDATED = "updated"
    COMPLETED = "completed"
    DELETED = "deleted"
    RESCHEDULED = "rescheduled"
