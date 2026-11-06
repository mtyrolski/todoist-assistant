"""Resolve saved and inferred project adjustment mappings."""

from typing import Any, cast


def _preferred_adjustment_project_id(
    project_name: str, project_records: list[dict[str, Any]]
) -> str | None:
    matches = [
        record for record in project_records if record.get("name") == project_name
    ]
    active_matches = [record for record in matches if not record.get("isArchived")]
    preferred = active_matches or matches
    if len(preferred) != 1:
        return None
    return str(preferred[0]["id"])


def _resolve_automatic_project_mappings(
    project_records: list[dict[str, Any]],
    *,
    manual_mappings: dict[str, str],
    archived_parent_projects: set[str],
) -> tuple[dict[str, str], list[dict[str, str | None]]]:
    """Infer archived-project root assignments not overridden by saved mappings."""

    candidates: dict[str, set[str]] = {}
    candidate_details: list[dict[str, str | None]] = []
    for record in project_records:
        if not record.get("isArchived"):
            continue
        source_name = str(record.get("name") or "")
        if (
            not source_name
            or source_name in manual_mappings
            or source_name in archived_parent_projects
        ):
            continue
        ancestors = cast(list[dict[str, str]], record.get("ancestors") or [])
        if not ancestors:
            continue

        promoted_parent = next(
            (
                ancestor
                for ancestor in ancestors
                if ancestor["name"] in archived_parent_projects
            ),
            None,
        )
        manual_ancestor = next(
            (ancestor for ancestor in ancestors if ancestor["name"] in manual_mappings),
            None,
        )
        if promoted_parent is not None:
            target_name = promoted_parent["name"]
            target_id = promoted_parent["id"]
        elif manual_ancestor is not None:
            target_name = manual_mappings[manual_ancestor["name"]]
            target_id = _preferred_adjustment_project_id(target_name, project_records)
        else:
            target_name = str(record.get("rootName") or "")
            target_id = str(record.get("rootId") or "") or None
        if not target_name or target_name == source_name:
            continue

        candidates.setdefault(source_name, set()).add(target_name)
        candidate_details.append(
            {
                "sourceProject": source_name,
                "sourceProjectId": str(record.get("id") or "") or None,
                "parentProject": target_name,
                "parentProjectId": target_id,
                "provenance": "automatic",
            }
        )

    automatic_mappings = {
        source_name: next(iter(target_names))
        for source_name, target_names in sorted(candidates.items())
        if len(target_names) == 1
    }
    details = [
        detail
        for detail in candidate_details
        if automatic_mappings.get(str(detail["sourceProject"]))
        == detail["parentProject"]
    ]
    return automatic_mappings, details


def _manual_project_mapping_details(
    project_records: list[dict[str, Any]], manual_mappings: dict[str, str]
) -> list[dict[str, str | None]]:
    details: list[dict[str, str | None]] = []
    for source_name, target_name in sorted(manual_mappings.items()):
        source_records = [
            record for record in project_records if record.get("name") == source_name
        ] or [{}]
        target_id = _preferred_adjustment_project_id(target_name, project_records)
        for record in source_records:
            details.append(
                {
                    "sourceProject": source_name,
                    "sourceProjectId": str(record.get("id") or "") or None,
                    "parentProject": target_name,
                    "parentProjectId": target_id,
                    "provenance": "manual",
                }
            )
    return details


