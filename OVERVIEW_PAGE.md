# Overview Dashboard Page

## Description

The **Overview** page provides a comprehensive, single-page productivity dashboard that consolidates the most important insights from your Todoist data. This page is designed to give you a complete picture of your productivity patterns, current state, and progress trends at a glance.

## Features

### 📊 Productivity Overview
- **Key Metrics**: Events, Completed Tasks, Added Tasks, and Rescheduled Tasks with percentage changes
- **Priority Badges**: Visual breakdown of tasks by priority levels (P1-P4)
- **Date Range**: Configurable time period for analysis

### 🎯 Activity Insights
Three-column layout showing:
- **Current Task Types**: Distribution of tasks by due date categories
- **Popular Labels**: Most frequently used labels across projects
- **Event Types Distribution**: Pie chart of activity types (added, completed, updated, etc.)

### ⏰ Time & Activity Patterns
- **Activity Heatmap**: When you're most productive throughout the week and day
- **Top Active Projects**: Projects with the highest activity levels

### 📈 Progress Trends
- **Events Over Time**: Daily activity breakdown with 7-day rolling averages by activity type
- **Cumulative Task Completion**: Progress tracking by project over time

### 💡 Quick Insights
- Total active tasks and projects summary
- Average daily activity rate
- Most active project identification

## Layout Philosophy

The Overview page follows a logical information hierarchy:

1. **Metrics First**: Key performance indicators at the top
2. **Current State**: What's happening now with your tasks and projects
3. **Patterns**: When and how you work most effectively
4. **Trends**: Progress over time to track improvement
5. **Actionable Insights**: Quick takeaways for productivity optimization

## Usage

The Overview page is the first option in the navigation menu and serves as the primary dashboard entry point. It's designed to answer the most common productivity questions:

- How am I performing this period vs. last period?
- What's my current task distribution?
- When am I most productive?
- Which projects are getting the most attention?
- Am I making progress over time?

## Technical Implementation

- **Efficient Layout**: Uses Streamlit's column system for optimal space utilization
- **Cached Data**: All plot functions are cached for fast loading
- **Responsive Design**: Charts automatically adjust to container width
- **Dark Mode Compatible**: All visualizations work well in dark themes

## Navigation

Access the Overview page by selecting "Overview" from the sidebar navigation menu. The page will automatically load with your current date range and granularity settings from the sidebar controls.