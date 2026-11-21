"""Centralized Todoist constant definitions."""

from enum import StrEnum


class EventExtraField(StrEnum):
    CONTENT = "content"
    NAME = "name"
    DUE_DATE = "due_date"
    LAST_DUE_DATE = "last_due_date"


class EventType(StrEnum):
    ADDED = "added"
    UPDATED = "updated"
    COMPLETED = "completed"
    UNCOMPLETED = "uncompleted"
    DELETED = "deleted"
    RESCHEDULED = "rescheduled"
