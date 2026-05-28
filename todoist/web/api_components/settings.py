from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from omegaconf import DictConfig, OmegaConf

from todoist.automations.multiplicate.automation import MultiplyConfig
from todoist.stale_tasks import StaleTaskConfig
from todoist.web.dashboard_payload import DEFAULT_URGENCY_SETTINGS, normalize_plot_events


def llm_breakdown_settings_payload(config: DictConfig) -> dict[str, Any]:
    raw = config.get("llm_breakdown") if hasattr(config, "get") else None
    data = OmegaConf.to_container(raw, resolve=False) if raw is not None else {}
    if not isinstance(data, dict):
        data = {}

    variants_raw = data.get("variants") or {}
    variants: dict[str, Any] = {}
    if isinstance(variants_raw, Mapping):
        for key, value in variants_raw.items():
            if not isinstance(value, Mapping):
                continue
            variants[str(key)] = {
                "instruction": value.get("instruction", ""),
                "maxDepth": value.get("max_depth"),
                "maxChildren": value.get("max_children"),
                "queueDepth": value.get("queue_depth"),
            }

    return {
        "labelPrefix": data.get("label_prefix", "ai-"),
        "defaultVariant": data.get("default_variant", "breakdown"),
        "maxDepth": data.get("max_depth", 3),
        "maxChildren": data.get("max_children", 6),
        "maxTotalTasks": data.get("max_total_tasks", 60),
        "maxQueueDepth": data.get("max_queue_depth", 1),
        "autoQueueChildren": data.get("auto_queue_children", True),
        "variants": variants,
    }


def multiplication_settings_payload(config: DictConfig) -> dict[str, Any]:
    raw = config.get("multiply") if hasattr(config, "get") else None
    data = OmegaConf.to_container(raw, resolve=False) if raw is not None else {}
    if not isinstance(data, dict):
        data = {}

    defaults = MultiplyConfig()
    config_data = data.get("config") if isinstance(data.get("config"), Mapping) else {}
    if not isinstance(config_data, Mapping):
        config_data = {}

    return {
        "flatLeafTemplate": config_data.get(
            "flat_leaf_template", defaults.flat_leaf_template
        ),
        "deepLeafTemplate": config_data.get(
            "deep_leaf_template", defaults.deep_leaf_template
        ),
        "flatLabelRegex": config_data.get(
            "flat_label_regex", defaults.flat_label_regex
        ),
        "deepLabelRegex": config_data.get(
            "deep_label_regex", defaults.deep_label_regex
        ),
        "deepChildLabel": config_data.get(
            "deep_child_label",
            defaults.deep_child_label,
        ),
        "cleanupUnusedLabels": bool(
            config_data.get("cleanup_unused_labels", defaults.cleanup_unused_labels)
        ),
        "cleanupUnusedLabelsAfterDays": config_data.get(
            "cleanup_unused_labels_after_days",
            defaults.cleanup_unused_labels_after_days,
        ),
    }


def stale_tasks_settings_payload(config: DictConfig) -> dict[str, Any]:
    raw = config.get("stale_tasks") if hasattr(config, "get") else None
    data = OmegaConf.to_container(raw, resolve=False) if raw is not None else {}
    if not isinstance(data, dict):
        data = {}

    defaults = StaleTaskConfig()
    config_data = data.get("config") if isinstance(data.get("config"), Mapping) else {}
    if not isinstance(config_data, Mapping):
        config_data = {}

    return {
        "oldAfterDays": config_data.get("old_after_days", defaults.old_after_days),
        "veryOldAfterDays": config_data.get(
            "very_old_after_days",
            defaults.very_old_after_days,
        ),
        "warningLabel": config_data.get("old_label", defaults.old_label),
        "veryOldLabel": config_data.get("very_old_label", defaults.very_old_label),
        "deleteAfterWarningDays": config_data.get(
            "delete_after_warning_days",
            defaults.delete_after_warning_days,
        ),
        "dryRun": bool(data.get("dry_run", True)),
        "maxUpdatesPerTick": data.get("max_updates_per_tick", 25),
    }


def dashboard_settings_payload(
    config: DictConfig, *, dashboard_config_path: Path, repo_root: Path
) -> dict[str, Any]:
    raw = config.get("urgency") if hasattr(config, "get") else None
    data = OmegaConf.to_container(raw, resolve=False) if raw is not None else {}
    if not isinstance(data, dict):
        data = {}
    defaults = DEFAULT_URGENCY_SETTINGS
    badge_labels = data.get("badge_labels") if isinstance(data.get("badge_labels"), Mapping) else {}
    badge_labels = badge_labels if isinstance(badge_labels, Mapping) else {}
    thresholds = data.get("warn_priority_thresholds")
    if not isinstance(thresholds, list):
        thresholds = list(defaults["warn_priority_thresholds"])
    fire_labels = data.get("fire_labels")
    if not isinstance(fire_labels, list):
        fire_label_value = str(data.get("fire_label", defaults["fire_label"])).strip()
        fire_labels = [fire_label_value] if fire_label_value else list(defaults["fire_labels"])
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
