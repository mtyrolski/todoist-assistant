"""Validated dashboard patches, independent of route globals and file IO."""

from collections.abc import Mapping
from datetime import date
from typing import Annotated, Any

from fastapi import HTTPException
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictStr,
    ValidationError,
    field_validator,
)

Count = Annotated[int, Field(strict=True, ge=1, le=100_000)]
Days = Annotated[int, Field(strict=True, ge=0, le=100_000)]
Priority = Annotated[int, Field(strict=True, ge=1, le=4)]


class PlotEventSetting(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    date: Annotated[StrictStr, Field(pattern=r"^\d{4}-\d{2}-\d{2}$")]
    label: Annotated[StrictStr, Field(min_length=1, max_length=200)]
    color: Annotated[StrictStr, Field(pattern=r"^#[0-9a-fA-F]{6}$")] = "#ff6b7a"

    @field_validator("date")
    @classmethod
    def valid_calendar_date(cls, value: str) -> str:
        date.fromisoformat(value)
        return value


class BadgeLabels(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    good: StrictStr = "OK"
    warn: StrictStr = "Watch"
    danger: StrictStr = "Urgent"


class DashboardSettingsPatch(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    enabled: StrictBool = True
    fireLabel: StrictStr = ""
    fireLabels: list[StrictStr] = Field(default_factory=list)
    warnPriorityThresholds: list[Priority] = Field(default_factory=list)
    warnPriorityMinCount: Count = 1
    warnDueWithinDays: Days = 0
    warnDueMinCount: Count = 1
    warnDeadlineWithinDays: Days = 0
    warnDeadlineMinCount: Count = 1
    dangerOnFireLabel: StrictBool = True
    warnOnPriority: StrictBool = True
    warnOnDue: StrictBool = True
    warnOnDeadline: StrictBool = True
    warnSummaryLabel: StrictStr = "Attention needed"
    dangerSummaryLabel: StrictStr = "Urgent attention needed"
    badgeLabels: BadgeLabels = Field(default_factory=BadgeLabels)
    plotEvents: list[PlotEventSetting] = Field(default_factory=list)


def parse_settings_patch(payload: dict[str, Any]) -> dict[str, Any]:
    try:
        return DashboardSettingsPatch.model_validate(payload).model_dump(
            exclude_unset=True
        )
    except ValidationError as exc:
        error = exc.errors(include_url=False)[0]
        field = ".".join(str(part) for part in error["loc"])
        raise HTTPException(status_code=400, detail=f"{field}: {error['msg']}") from exc


def apply_settings_patch(config: Any, patch: dict[str, Any]) -> None:
    """Apply an already validated partial update without overwriting other rules."""
    raw = config.get("urgency")
    urgency = dict(raw) if isinstance(raw, Mapping) else {}
    for name, value in patch.items():
        if name == "plotEvents":
            config["plot_events"] = value
            continue
        snake_name = "".join(
            "_" + char.lower() if char.isupper() else char for char in name
        )
        if name == "badgeLabels":
            value = {**dict(urgency.get("badge_labels") or {}), **value}
        elif name == "fireLabels":
            value = list(
                dict.fromkeys(label.strip() for label in value if label.strip())
            )
            urgency["fire_label"] = value[0] if value else ""
        elif name == "warnPriorityThresholds":
            value = sorted(set(value), reverse=True)
        urgency[snake_name] = value
    config["urgency"] = urgency
