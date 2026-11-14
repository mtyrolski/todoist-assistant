from collections.abc import Mapping
from pathlib import Path
from typing import Any

from omegaconf import DictConfig, OmegaConf

from todometry.web.dashboard_payload import (
    DEFAULT_URGENCY_SETTINGS,
    normalize_plot_events,
)


def dashboard_settings_payload(
    config: DictConfig, *, dashboard_config_path: Path, repo_root: Path
) -> dict[str, Any]:
    raw = config.get("urgency") if hasattr(config, "get") else None
    data = OmegaConf.to_container(raw, resolve=False) if raw is not None else {}
    if not isinstance(data, dict):
        data = {}
    defaults = DEFAULT_URGENCY_SETTINGS
    badge_labels = (
        data.get("badge_labels")
        if isinstance(data.get("badge_labels"), Mapping)
        else {}
    )
    badge_labels = badge_labels if isinstance(badge_labels, Mapping) else {}
    thresholds = data.get("warn_priority_thresholds")
    if not isinstance(thresholds, list):
        thresholds = list(defaults["warn_priority_thresholds"])
    fire_labels = data.get("fire_labels")
    if not isinstance(fire_labels, list):
        fire_label_value = str(data.get("fire_label", defaults["fire_label"])).strip()
        fire_labels = (
            [fire_label_value] if fire_label_value else list(defaults["fire_labels"])
        )
    try:
        config_path = str(dashboard_config_path.relative_to(repo_root))
    except ValueError:
        config_path = str(dashboard_config_path)

    return {
        "enabled": bool(data.get("enabled", defaults["enabled"])),
        "fireLabel": data.get("fire_label", defaults["fire_label"]),
        "fireLabels": fire_labels,
        "warnPriorityThresholds": thresholds,
        "warnPriorityMinCount": data.get(
            "warn_priority_min_count", defaults["warn_priority_min_count"]
        ),
        "warnDueWithinDays": data.get(
            "warn_due_within_days", defaults["warn_due_within_days"]
        ),
        "warnDueMinCount": data.get(
            "warn_due_min_count", defaults["warn_due_min_count"]
        ),
        "warnDeadlineWithinDays": data.get(
            "warn_deadline_within_days", defaults["warn_deadline_within_days"]
        ),
        "warnDeadlineMinCount": data.get(
            "warn_deadline_min_count", defaults["warn_deadline_min_count"]
        ),
        "dangerOnFireLabel": bool(
            data.get("danger_on_fire_label", defaults["danger_on_fire_label"])
        ),
        "warnOnPriority": bool(
            data.get("warn_on_priority", defaults["warn_on_priority"])
        ),
        "warnOnDue": bool(data.get("warn_on_due", defaults["warn_on_due"])),
        "warnOnDeadline": bool(
            data.get("warn_on_deadline", defaults["warn_on_deadline"])
        ),
        "warnSummaryLabel": data.get(
            "warn_summary_label", defaults["warn_summary_label"]
        ),
        "dangerSummaryLabel": data.get(
            "danger_summary_label", defaults["danger_summary_label"]
        ),
        "badgeLabels": {
            "good": badge_labels.get("good", defaults["badge_labels"]["good"]),
            "warn": badge_labels.get("warn", defaults["badge_labels"]["warn"]),
            "danger": badge_labels.get("danger", defaults["badge_labels"]["danger"]),
        },
        "plotEvents": normalize_plot_events(config),
        "configPath": config_path,
    }
