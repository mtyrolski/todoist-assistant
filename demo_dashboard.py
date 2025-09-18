"""
Simplified demonstration of the new one-page dashboard layout.
This shows the improved layout design without requiring the full backend.
"""

import pandas as pd
import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
import numpy as np
from datetime import datetime, timedelta

# Configure page
st.set_page_config(page_title="Todoist Dashboard - New Layout", layout="wide")

def create_sample_heatmap():
    """Create a sample activity heatmap"""
    np.random.seed(42)
    # Create sample data for 24 hours x 7 days
    hours = list(range(24))
    days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
    
    # Generate sample activity data (higher during work hours)
    data = np.random.poisson(3, (7, 24))
    for i in range(7):  # Add patterns
        for j in range(24):
            if 9 <= j <= 17 and i < 5:  # Work hours on weekdays
                data[i][j] = np.random.poisson(8)
            elif 18 <= j <= 22:  # Evening hours
                data[i][j] = np.random.poisson(5)
            elif j < 7 or j > 23:  # Late/early hours
                data[i][j] = np.random.poisson(1)
    
    fig = go.Figure(data=go.Heatmap(
        z=data,
        x=hours,
        y=days,
        colorscale='blues',
        showscale=True
    ))
    
    fig.update_layout(
        title='Activity Heatmap: Events by Day and Hour',
        xaxis_title='Hour of Day',
        yaxis_title='Day of Week',
        height=300
    )
    
    return fig

def create_sample_pie_chart(title, labels, values):
    """Create a sample pie chart"""
    fig = go.Figure(data=[go.Pie(labels=labels, values=values, hole=.3)])
    fig.update_layout(title_text=title, height=300)
    return fig

def create_sample_line_chart(title):
    """Create a sample line chart"""
    dates = pd.date_range(start='2024-01-01', end='2024-12-31', freq='W')
    values = np.random.randint(10, 50, len(dates))
    values = pd.Series(values).rolling(window=4).mean()  # Smooth the line
    
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=dates, y=values, mode='lines+markers', name='Events'))
    fig.update_layout(title=title, height=300)
    return fig

def create_sample_bar_chart(title):
    """Create a sample bar chart"""
    projects = ['Work Project', 'Personal Tasks', 'Learning', 'Health & Fitness', 'Side Projects']
    values = [45, 32, 28, 15, 22]
    
    fig = go.Figure(data=[go.Bar(x=projects, y=values)])
    fig.update_layout(title=title, height=300)
    return fig

def main():
    """Main dashboard function"""
    
    # ===== TITLE =====
    st.title("🏠 Home Dashboard - New Comprehensive Layout")
    
    # ===== TOP SECTION: KEY METRICS AND BADGES =====
    st.markdown("### 📊 **Productivity Overview**")
    
    # Priority badges for quick status overview
    st.markdown("""
    :red-badge[P1 tasks 5🔥] :orange-badge[P2 tasks 12 ⚠️] :blue-badge[P3 tasks 18 🔵] :gray-badge[P4 tasks 7 ⚽]
    """)
    
    # Key metrics in a single row
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric(label="Events", value="156", delta="12%", border=True)
    with col2:
        st.metric(label="Completed Tasks", value="42", delta="8%", border=True) 
    with col3:
        st.metric(label="Added Tasks", value="28", delta="15%", border=True)
    with col4:
        st.metric(label="Rescheduled Tasks", value="7", delta="-3%", delta_color="inverse", border=True)
    
    # ===== MAIN DASHBOARD GRID =====
    st.markdown("---")
    
    # Row 1: Activity Heatmap (full width) - Most important insight
    st.markdown("### 🕒 **Activity Patterns**")
    st.plotly_chart(create_sample_heatmap(), use_container_width=True)
    
    # Row 2: Current Status (2 columns)
    st.markdown("### 📋 **Current Status**")
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**🎯 Task Types Distribution**")
        task_types = ['Overdue', 'Today', 'Tomorrow', 'This Week', 'Later']
        task_values = [8, 15, 12, 25, 18]
        st.plotly_chart(create_sample_pie_chart("Current Tasks Types", task_types, task_values), 
                        use_container_width=True)
    with col2:
        st.markdown("**🏷️ Most Popular Labels**")
        label_types = ['Work', 'Personal', 'Urgent', 'Learning', 'Health']
        label_values = [35, 28, 15, 12, 10]
        st.plotly_chart(create_sample_pie_chart("Most Popular Labels", label_types, label_values), 
                        use_container_width=True)
    
    # Row 3: Progress Trends (2 columns)
    st.markdown("### 📈 **Progress Trends**")
    col3, col4 = st.columns(2)
    with col3:
        st.markdown("**📊 Events Over Time**")
        st.plotly_chart(create_sample_line_chart("Events Over Time"), use_container_width=True)
    with col4:
        st.markdown("**📂 Top Projects by Activity**")
        st.plotly_chart(create_sample_bar_chart("Top Projects by Events"), use_container_width=True)
    
    # Row 4: Completion Analysis (2 columns)
    st.markdown("### ✅ **Completion Analysis**")
    col5, col6 = st.columns(2)
    with col5:
        st.markdown("**📝 Completed Tasks by Period**")
        st.plotly_chart(create_sample_line_chart("Completed Tasks per Week"), use_container_width=True)
    with col6:
        st.markdown("**📈 Cumulative Progress**")
        st.plotly_chart(create_sample_line_chart("Cumulative Completed Tasks"), use_container_width=True)
    
    # ===== FOOTER =====
    st.markdown("---")
    st.markdown("**✨ New Layout Benefits:**")
    st.markdown("""
    - **Higher Information Density**: More insights visible at once
    - **Visual Hierarchy**: Most important information (activity patterns) prominently displayed
    - **Actionable Overview**: Priority badges and metrics provide immediate status
    - **Strategic Grid Layout**: Related visualizations grouped logically
    - **Reduced Scrolling**: Compact 2-column design maximizes screen real estate
    """)

if __name__ == '__main__':
    main()