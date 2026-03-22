# Script for making data anonymous for demo purposes.
import hashlib
from collections.abc import Sequence
from dataclasses import dataclass
from typing import cast

import pandas as pd

from todoist.types import Project

@dataclass(frozen=True)
class _ProjectTheme:
    root_name: str
    role_levels: tuple[tuple[str, ...], ...]


_GENERIC_ROLE_LEVELS: tuple[tuple[str, ...], ...] = (
    ("Inbox", "Backlog", "Notes", "Planning", "Tasks", "Ideas", "Archive", "Follow-up"),
    ("Checklist", "Queue", "References", "Milestones", "Admin", "Review", "Someday", "Parking Lot"),
    ("Drafts", "Next Steps", "Resources", "Open Loops", "Prep", "Recap", "History", "Details"),
)

_PROJECT_THEME_CATALOG: tuple[_ProjectTheme, ...] = (
    _ProjectTheme(
        "North Star Studio",
        (
            ("Recordings", "First Album", "Office", "Rehearsal", "Mixing", "Merch", "Sessions", "Tour"),
            ("Song Ideas", "Tracklist", "Demos", "Artwork", "Release Prep", "Gear", "Guests", "Budget"),
            ("Lyrics", "Tasks", "References", "Notes", "Schedule", "Archive", "Assets", "Checklist"),
        ),
    ),
    _ProjectTheme(
        "Health",
        (
            ("Workout", "Vitamins", "Sleep", "Nutrition", "Checkups", "Recovery", "Mobility", "Routine"),
            ("Weekly Plan", "Habits", "Measurements", "Appointments", "Shopping", "Research", "Coach", "Notes"),
            ("Exercises", "Meals", "Supplements", "Questions", "Logs", "Milestones", "Results", "Archive"),
        ),
    ),
    _ProjectTheme(
        "Home Base",
        (
            ("Repairs", "Kitchen", "Bills", "Cleaning", "Garden", "Storage", "Shopping", "Decor"),
            ("This Week", "Supplies", "Quotes", "Seasonal", "Appliances", "Paperwork", "Wishlist", "Notes"),
            ("Checklist", "Receipts", "Measurements", "Ideas", "Contacts", "Tasks", "Archive", "Plans"),
        ),
    ),
    _ProjectTheme(
        "Learning Lab",
        (
            ("Courses", "Practice", "Reading List", "Notes", "Projects", "Review", "Milestones", "Ideas"),
            ("Week 1", "Exercises", "Bookmarks", "Examples", "Questions", "Flashcards", "Goals", "Archive"),
            ("Concepts", "Resources", "Homework", "Experiments", "Summaries", "Tasks", "References", "Recap"),
        ),
    ),
    _ProjectTheme(
        "Travel Plans",
        (
            ("Flights", "Hotels", "Itinerary", "Packing", "Budget", "Day Trips", "Food Spots", "Documents"),
            ("Booking", "Maps", "Reservations", "Ideas", "Checklist", "Transit", "Photos", "Notes"),
            ("Tickets", "Addresses", "Contacts", "Backup", "Tasks", "References", "Archive", "Expenses"),
        ),
    ),
    _ProjectTheme(
        "Family Hub",
        (
            ("Calendar", "School", "Birthdays", "Weekend Plans", "Paperwork", "Shopping", "Trips", "Notes"),
            ("This Month", "Appointments", "Lists", "Ideas", "Photos", "Household", "Budget", "Archive"),
            ("Tasks", "Contacts", "Checklist", "Memories", "References", "Prep", "Follow-up", "Recap"),
        ),
    ),
    _ProjectTheme(
        "Writing Desk",
        (
            ("Drafts", "Essays", "Newsletter", "Ideas", "Editing", "Research Notes", "Pitch List", "Archive"),
            ("Outlines", "Sources", "Deadlines", "Rewrites", "Submissions", "Clippings", "Prompts", "Notes"),
            ("Openers", "Quotes", "Checklist", "Tasks", "References", "Versions", "Feedback", "Recap"),
        ),
    ),
    _ProjectTheme(
        "Money Map",
        (
            ("Budget", "Bills", "Savings", "Taxes", "Investing", "Subscriptions", "Admin", "Goals"),
            ("Monthly Plan", "Receipts", "Accounts", "Questions", "Renewals", "Transfers", "Wishlist", "Notes"),
            ("Checklist", "Statements", "Tasks", "References", "History", "Forecast", "Archive", "Details"),
        ),
    ),
)
_LABEL_NAMES = (
    "Work",
    "Personal",
    "Urgent",
    "Important",
    "Shopping",
    "Travel",
    "Fitness",
    "Health",
    "Family",
    "Friends",
    "Projects",
    "Ideas",
    "Goals",
    "Hobbies",
    "Learning",
    "Reading",
    "Writing",
    "Cooking",
    "DIY",
    "Finance",
    "Budgeting",
    "Home",
    "Garden",
    "Pets",
    "Events",
    "Social",
    "Volunteer",
    "Fitness Goals",
    "Travel Plans",
)
@dataclass(frozen=True)
class _ProjectTreeNode:
    project: Project
    children: tuple["_ProjectTreeNode", ...]


def _project_sort_key(project: Project) -> tuple[int, str, str]:
    return (
        int(project.project_entry.child_order or 0),
        project.project_entry.name.casefold(),
        project.id,
    )


def _collect_activity_project_names(df_activity: pd.DataFrame) -> list[str]:
    project_names: set[str] = set()
    for column in ("parent_project_name", "root_project_name"):
        if column not in df_activity.columns:
            continue
        values = df_activity[column].dropna().astype(str)
        project_names.update(value for value in values if value)
    return sorted(project_names)


def _build_project_tree(active_projects: Sequence[Project]) -> tuple[list[_ProjectTreeNode], dict[str, _ProjectTreeNode]]:
    projects_by_id = {project.id: project for project in active_projects}
    children_by_parent: dict[str | None, list[Project]] = {}
    for project in active_projects:
        parent_id = project.project_entry.parent_id
        if parent_id is not None and parent_id not in projects_by_id:
            parent_id = None
        children_by_parent.setdefault(parent_id, []).append(project)

    for siblings in children_by_parent.values():
        siblings.sort(key=_project_sort_key)

    node_cache: dict[str, _ProjectTreeNode] = {}

    def _build_node(project: Project) -> _ProjectTreeNode:
        cached = node_cache.get(project.id)
        if cached is not None:
            return cached
        node = _ProjectTreeNode(
            project=project,
            children=tuple(_build_node(child) for child in children_by_parent.get(project.id, [])),
        )
        node_cache[project.id] = node
        return node

    roots = tuple(_build_node(project) for project in children_by_parent.get(None, []))
    return list(roots), node_cache


def _select_root_theme(root_index: int) -> _ProjectTheme:
    theme = _PROJECT_THEME_CATALOG[root_index % len(_PROJECT_THEME_CATALOG)]
    cycle = root_index // len(_PROJECT_THEME_CATALOG)
    if cycle == 0:
        return theme
    return _ProjectTheme(
        root_name=f"{theme.root_name} {cycle + 1}",
        role_levels=theme.role_levels,
    )


def _select_role(theme: _ProjectTheme, depth: int, sibling_index: int, root_index: int) -> str:
    role_levels = theme.role_levels or _GENERIC_ROLE_LEVELS
    role_pool = role_levels[min(depth - 1, len(role_levels) - 1)]
    position = sibling_index + (root_index % len(role_pool))
    role = role_pool[position % len(role_pool)]
    cycle = position // len(role_pool)
    if cycle == 0:
        return role
    return f"{role} {cycle + 1}"


def _build_project_name_mapping(active_projects: Sequence[Project], project_names: Sequence[str]) -> dict[str, str]:
    roots, _ = _build_project_tree(active_projects)
    mapping: dict[str, str] = {}

    def _assign_node(node: _ProjectTreeNode, theme: _ProjectTheme, role_path: tuple[str, ...], root_index: int) -> None:
        anonymized_name = theme.root_name if not role_path else " / ".join((theme.root_name, *role_path))
        mapping[node.project.project_entry.name] = anonymized_name
        for child_index, child in enumerate(node.children):
            role = _select_role(theme, len(role_path) + 1, child_index, root_index)
            _assign_node(child, theme, role_path + (role,), root_index)

    for root_index, node in enumerate(roots):
        _assign_node(node, _select_root_theme(root_index), (), root_index)

    for project_name in project_names:
        if project_name in mapping:
            continue
        digest = hashlib.sha256(project_name.encode("utf-8")).digest()
        fallback_index = int.from_bytes(digest[:8], "big")
        mapping[project_name] = _PROJECT_THEME_CATALOG[fallback_index % len(_PROJECT_THEME_CATALOG)].root_name

    return mapping


def _replace_project_names(df_activity: pd.DataFrame, project_mapping: dict[str, str]) -> None:
    for column in ("parent_project_name", "root_project_name"):
        if column not in df_activity.columns:
            continue
        df_activity.loc[:, column] = df_activity[column].map(lambda name: project_mapping.get(name, name))


def anonymize_label_names(active_projects: list[Project]) -> dict[str, str]:
    """
    Anonymize label names deterministically and return the replacement mapping.
    """
    all_labels_names = sorted({
        label for project in active_projects for task in project.tasks for label in task.task_entry.labels
    })

    if len(all_labels_names) > len(_LABEL_NAMES):
        raise ValueError("Not enough unique names to anonymize all labels.")

    label_mapping: dict[str, str] = {
        original: str(replacement)
        for original, replacement in zip(all_labels_names, _LABEL_NAMES)
    }

    for project in active_projects:
        for task in project.tasks:
            task.task_entry.labels = [label_mapping.get(label, label) for label in task.task_entry.labels]

    return label_mapping


def anonymize_project_names(
    df_activity: pd.DataFrame,
    active_projects: Sequence[Project] | None = None,
) -> dict[str, str]:
    """
    Anonymize project names in the activity dataframe using themed hierarchy paths.
    """
    project_names = _collect_activity_project_names(df_activity)
    project_mapping = _build_project_name_mapping(active_projects or (), project_names)
    _replace_project_names(df_activity, project_mapping)
    return project_mapping


def anonymize_activity_dates(df_activity: pd.DataFrame, *, seed: str = "todoist-demo") -> pd.DataFrame:
    """
    Anonymize event timestamps by shifting each task's timeline to a stable random target.
    This preserves per-task durations while removing real-world temporal trends.
    """
    if df_activity.empty or not isinstance(df_activity.index, pd.DatetimeIndex):
        return df_activity

    task_col = "task_id" if "task_id" in df_activity.columns else "parent_item_id" if "parent_item_id" in df_activity.columns else None
    if task_col is None or "id" not in df_activity.columns:
        return df_activity

    global_min = df_activity.index.min()
    global_max = df_activity.index.max()
    if not isinstance(global_min, pd.Timestamp) or not isinstance(global_max, pd.Timestamp):
        return df_activity
    global_min_ts = cast(pd.Timestamp, global_min)
    global_max_ts = cast(pd.Timestamp, global_max)
    if global_min_ts == global_max_ts:
        return df_activity

    zero_delta = cast(pd.Timedelta, pd.Timedelta(0))
    task_key = df_activity[task_col].where(df_activity[task_col].notna(), df_activity["id"]).astype(str)
    df = df_activity.copy()

    def _stable_fraction(value: str) -> float:
        digest = hashlib.sha256(f"{seed}:{value}".encode("utf-8")).digest()
        return int.from_bytes(digest[:8], "big") / 2**64

    offsets: dict[str, pd.Timedelta] = {}
    for key, group in df.groupby(task_key, sort=False):
        key_str = str(key)
        if group.empty:
            continue
        anchor = group.index.max()
        if "type" in group.columns:
            completed = group[group["type"] == "completed"]
            if not completed.empty:
                anchor = completed.index.max()
        task_min = group.index.min()
        task_max = group.index.max()
        if not isinstance(anchor, pd.Timestamp):
            offsets[key_str] = zero_delta
            continue
        if not isinstance(task_min, pd.Timestamp) or not isinstance(task_max, pd.Timestamp):
            offsets[key_str] = zero_delta
            continue
        anchor_ts = cast(pd.Timestamp, anchor)
        task_min_ts = cast(pd.Timestamp, task_min)
        task_max_ts = cast(pd.Timestamp, task_max)
        pre_span = cast(pd.Timedelta, anchor_ts - task_min_ts).total_seconds()
        post_span = cast(pd.Timedelta, task_max_ts - anchor_ts).total_seconds()
        available_start = cast(pd.Timestamp, global_min_ts + pd.Timedelta(seconds=pre_span))
        available_end = cast(pd.Timestamp, global_max_ts - pd.Timedelta(seconds=post_span))
        if available_end <= available_start:
            offsets[key_str] = zero_delta
            continue
        fraction = _stable_fraction(key_str)
        available_span = cast(pd.Timedelta, available_end - available_start)
        target = cast(
            pd.Timestamp,
            available_start + pd.Timedelta(seconds=available_span.total_seconds() * fraction),
        )
        offsets[key_str] = cast(pd.Timedelta, target - anchor_ts)

    offset_series = task_key.map(lambda value: offsets.get(str(value), zero_delta)).fillna(zero_delta)
    df.index = df.index + pd.to_timedelta(offset_series.to_numpy())
    df.sort_index(inplace=True)
    return df
