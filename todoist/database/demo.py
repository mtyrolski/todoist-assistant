# Script for making data anonymous for demo purposes.
import pandas as pd
import random

from todoist.types import Project

_available_project_names = [
    'Travel Journal', 'Recipe Explorer', 'Workout Tracker', 'Budget Buddy', 
    'Movie Night Planner', 'Bookworm Haven', 'Daily Habit Builder', 
    'Fitness Goals Dashboard', 'Coding Playground', 'DIY Planner', 
    'Home Automation Hub', 'Photography Portfolio', 'Language Learning Log', 
    'Virtual Garden', 'Bucket List', 'Family Tree Builder', 'Pet Care Tracker', 
    'Craft Projects', 'Personal Finance Planner', 'Digital Scrapbook', 
    'Foodie Adventures', 'Minimalist To-Do', 'Journaling Companion', 
    'Art Gallery', 'Passion Project Tracker', 'Hiking Trails Log', 
    'Self-Care Scheduler', 'Dream Journal', 'Weekend Planner', 
    'Music Library', 'Mood Tracker', 'Weather Watcher', 'Space Explorer', 
    'Trivia Master', 'Stock Portfolio', 'Meditation Guide', 'Grocery List', 
    'Meal Planner', 'Event Scheduler', 'Gift Tracker', 'Fitness Timer', 
    'Reading Tracker', 'Expense Splitter', 'Travel Budgeter', 'Pet Health Log', 
    'Art Studio', 'Video Collage', 'Idea Journal', 'Yoga Routine', 
    'Startup Planner', 'Fitness Challenges', 'Mindfulness App', 'Project Tracker', 
    'Tech News Feed', 'Resume Builder', 'Job Applications', 'Time Capsule', 
    'Budget Calculator', 'Home Inventory', 'Car Maintenance', 'Wedding Planner', 
    'Holiday Countdown', 'Personal Diary', 'Plant Watering Log', 'Game Collection', 
    'Recipe Organizer', 'Gift Ideas', 'Learning Tracker', 'Study Planner', 
    'Music Playlist', 'Photo Editor', 'Fitness Planner', 'Mood Diary', 
    'Pet Adoption', 'Goal Achiever', 'Skill Tracker', 'Food Journal', 
    'Book Club', 'Workout Timer', 'Startup Ideas', 'Fitness Journal', 
    'Simple Notes', 'Craft Planner', 'Weight Tracker', 'Travel Planner', 
    'Dream Catcher', 'Hobby Finder', 'Sleep Tracker', 'Health Journal', 
    'Daily Quotes', 'Daily Reflections', 'Habit Tracker', 'Chore Organizer', 
    'Personal Assistant', 'Work Journal', 'Daily Gratitude', 'Mind Map', 
    'Tech Blog', 'Household Planner', 'Daily Planner', 'Task Manager', 
    'Recipe Compiler', 'Pet Tracker', 'Social Scheduler', 'Memory Book', 
    'Travel Memories', 'Language Notes', 'Fitness Monitor', 'Daily Goals', 
    'Creative Journal', 'Adventure Log', 'Design Portfolio', 'Movie Ratings', 
    'Quick Recipes', 'Workout Log', 'Savings Tracker', 'Side Project', 
    'Life Organizer', 'Craft Log', 'Photo Album'
]
    
    
_available_label_names = [
    'Work', 'Personal', 'Urgent', 'Important', 'Shopping', 'Travel', 
    'Fitness', 'Health', 'Family', 'Friends', 'Projects', 'Ideas', 
    'Goals', 'Hobbies', 'Learning', 'Reading', 'Writing', 'Cooking', 
    'DIY', 'Finance', 'Budgeting', 'Home', 'Garden', 'Pets',
    'Events', 'Social', 'Volunteer', 'Fitness Goals', 'Travel Plans',
]

def anonymize_label_names(active_projects: list[Project]) -> dict[str, str]:
    """
    Anonymizes label names by replacing them in ori_label_names inplace plus returns
    mapping from original label names to anonymized ones.
    """
    all_labels_names = set(
        label for project in active_projects for task in project.tasks for label in task.task_entry.labels
    )
    
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
    
    df_activity.loc[:, 'parent_project_name'] = df_activity['parent_project_name'].map(anonymized_projects)
    df_activity.loc[:, 'root_project_name'] = df_activity['root_project_name'].map(anonymized_projects)
    
    return anonymized_projects