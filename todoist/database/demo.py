# Script for making data anonymous for demo purposes.
import hashlib
import random
from typing import cast

import pandas as pd

from todoist.types import Project

_available_project_names = [
    'Travel Journal', 'Recipe Explorer', 'Workout Tracker', 'Budget Buddy', 'Movie Night Planner', 'Bookworm Haven',
    'Daily Habit Builder', 'Fitness Goals Dashboard', 'Coding Playground', 'DIY Planner', 'Home Automation Hub',
    'Photography Portfolio', 'Language Learning Log', 'Virtual Garden', 'Bucket List', 'Family Tree Builder',
    'Pet Care Tracker', 'Craft Projects', 'Personal Finance Planner', 'Digital Scrapbook', 'Foodie Adventures',
    'Minimalist To-Do', 'Journaling Companion', 'Art Gallery', 'Passion Project Tracker', 'Hiking Trails Log',
    'Self-Care Scheduler', 'Dream Journal', 'Weekend Planner', 'Music Library', 'Mood Tracker', 'Weather Watcher',
    'Space Explorer', 'Trivia Master', 'Stock Portfolio', 'Meditation Guide', 'Grocery List', 'Meal Planner',
    'Event Scheduler', 'Gift Tracker', 'Fitness Timer', 'Reading Tracker', 'Expense Splitter', 'Travel Budgeter',
    'Pet Health Log', 'Art Studio', 'Video Collage', 'Idea Journal', 'Yoga Routine', 'Startup Planner',
    'Fitness Challenges', 'Mindfulness App', 'Project Tracker', 'Tech News Feed', 'Resume Builder', 'Job Applications',
    'Time Capsule', 'Budget Calculator', 'Home Inventory', 'Car Maintenance', 'Wedding Planner', 'Holiday Countdown',
    'Personal Diary', 'Plant Watering Log', 'Game Collection', 'Recipe Organizer', 'Gift Ideas', 'Learning Tracker',
    'Study Planner', 'Music Playlist', 'Photo Editor', 'Fitness Planner', 'Mood Diary', 'Pet Adoption', 'Goal Achiever',
    'Skill Tracker', 'Food Journal', 'Book Club', 'Workout Timer', 'Startup Ideas', 'Fitness Journal', 'Simple Notes',
    'Craft Planner', 'Weight Tracker', 'Travel Planner', 'Dream Catcher', 'Hobby Finder', 'Sleep Tracker',
    'Health Journal', 'Daily Quotes', 'Daily Reflections', 'Habit Tracker', 'Chore Organizer', 'Personal Assistant',
    'Work Journal', 'Daily Gratitude', 'Mind Map', 'Tech Blog', 'Household Planner', 'Daily Planner', 'Task Manager',
    'Recipe Compiler', 'Pet Tracker', 'Social Scheduler', 'Memory Book', 'Travel Memories', 'Language Notes',
    'Fitness Monitor', 'Daily Goals', 'Creative Journal', 'Adventure Log', 'Design Portfolio', 'Movie Ratings',
    'Quick Recipes', 'Workout Log', 'Savings Tracker', 'Side Project', 'Life Organizer', 'Craft Log', 'Photo Album'
]

_available_label_names = [
    'Work',
    'Personal',
    'Urgent',
    'Important',
    'Shopping',
    'Travel',
    'Fitness',
    'Health',
    'Family',
    'Friends',
    'Projects',
    'Ideas',
    'Goals',
    'Hobbies',
    'Learning',
    'Reading',
    'Writing',
    'Cooking',
    'DIY',
    'Finance',
    'Budgeting',
    'Home',
    'Garden',
    'Pets',
    'Events',
    'Social',
    'Volunteer',
    'Fitness Goals',
    'Travel Plans',
]


def anonymize_label_names(active_projects: list[Project]) -> dict[str, str]:
    """
    Anonymizes label names by replacing them in ori_label_names inplace plus returns
    mapping from original label names to anonymized ones.
    """
    all_labels_names = set(
        label for project in active_projects for task in project.tasks for label in task.task_entry.labels)

    ori_label_names = list(all_labels_names)

    # Ensure we have enough unique names to anonymize
    if len(ori_label_names) > len(_available_label_names):
        raise ValueError("Not enough unique names to anonymize all labels.")

    # Shuffle the available names and map them to original names
    random.shuffle(_available_label_names)
    # Create a mapping from original label names to anonymized names
    label_mapping = dict(zip(ori_label_names, _available_label_names))

    # Replace original label names with anonymized ones
    for project in active_projects:
        for task in project.tasks:
            task.task_entry.labels = list(map(lambda x: label_mapping.get(x, x), task.task_entry.labels))

    return label_mapping


def anonymize_project_names(df_activity: pd.DataFrame) -> dict[str, str]:
    """
    Anonymizes project names by replacing them in df_activity inplace plus returns
    mapping from original project names to anonymized ones.
    """
    project_names = df_activity['parent_project_name'].unique()
    project_mapping = random.sample(_available_project_names, len(project_names))
    anonymized_projects = dict(zip(project_names, project_mapping))

    df_activity.loc[:, 'parent_project_name'] = df_activity['parent_project_name'].map(
        lambda name: anonymized_projects.get(name, name)
    )
    df_activity.loc[:, 'root_project_name'] = df_activity['root_project_name'].map(
        lambda name: anonymized_projects.get(name, name)
    )

    return anonymized_projects


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
