"""Tests for TaskTemplate and from_config method."""

import pytest
from todoist.automations.template import TaskTemplate


class TestTaskTemplateFromConfig:
    """Tests for TaskTemplate.from_config class method."""

    def test_simple_config_parsing(self):
        """Test correct parsing of simple config dictionaries."""
        config = {
            'content': 'Test task',
            'description': 'Test description',
            'due_date_days_difference': 5,
            'priority': 3,
        }
        
        result = TaskTemplate.from_config(config)
        
        assert result.content == 'Test task'
        assert result.description == 'Test description'
        assert result.due_date_days_difference == 5
        assert result.priority == 3
        assert result.children == []

    def test_default_values_applied(self):
        """Test proper application of default values (priority=1, due_date_days_difference=0)."""
        config = {
            'content': 'Minimal task',
        }
        
        result = TaskTemplate.from_config(config)
        
        assert result.content == 'Minimal task'
        assert result.description is None
        assert result.due_date_days_difference == 0  # Default value
        assert result.priority == 1  # Default value
        assert result.children == []

    def test_recursive_processing_of_children(self):
        """Test recursive processing of children."""
        config = {
            'content': 'Parent task',
            'children': [
                {
                    'content': 'Child task 1',
                    'priority': 2,
                },
                {
                    'content': 'Child task 2',
                    'children': [
                        {
                            'content': 'Grandchild task',
                            'due_date_days_difference': 3,
                        }
                    ]
                }
            ]
        }
        
        result = TaskTemplate.from_config(config)
        
        assert result.content == 'Parent task'
        assert len(result.children) == 2
        
        # Check first child
        child1 = result.children[0]
        assert child1.content == 'Child task 1'
        assert child1.priority == 2
        assert child1.due_date_days_difference == 0  # Default
        assert child1.children == []
        
        # Check second child with its own children
        child2 = result.children[1]
        assert child2.content == 'Child task 2'
        assert len(child2.children) == 1
        
        # Check grandchild
        grandchild = child2.children[0]
        assert grandchild.content == 'Grandchild task'
        assert grandchild.due_date_days_difference == 3
        assert grandchild.priority == 1  # Default

    def test_already_instantiated_task_template(self):
        """Test handling of already-instantiated TaskTemplate objects."""
        existing_template = TaskTemplate(
            content='Existing task',
            description='Already instantiated',
            due_date_days_difference=7,
            priority=4,
            children=[]
        )
        
        result = TaskTemplate.from_config(existing_template)
        
        # Should return the same object
        assert result is existing_template
        assert result.content == 'Existing task'
        assert result.description == 'Already instantiated'
        assert result.due_date_days_difference == 7
        assert result.priority == 4

    def test_empty_children_list(self):
        """Test config with explicit empty children list."""
        config = {
            'content': 'Task with empty children',
            'children': [],
        }
        
        result = TaskTemplate.from_config(config)
        
        assert result.content == 'Task with empty children'
        assert result.children == []

    def test_none_description(self):
        """Test config with explicitly None description."""
        config = {
            'content': 'Task',
            'description': None,
        }
        
        result = TaskTemplate.from_config(config)
        
        assert result.description is None

    def test_mixed_children_configs_and_templates(self):
        """Test children list with mix of dicts and TaskTemplate instances."""
        child_template = TaskTemplate(
            content='Pre-instantiated child',
            priority=2,
        )
        
        config = {
            'content': 'Parent',
            'children': [
                {'content': 'Dict child'},
                child_template,
            ]
        }
        
        result = TaskTemplate.from_config(config)
        
        assert len(result.children) == 2
        assert result.children[0].content == 'Dict child'
        assert result.children[1] is child_template

    def test_content_is_none_from_config(self):
        """Test that content can be None when not provided (edge case)."""
        config = {
            'priority': 2,
            'due_date_days_difference': 1,
        }
        
        result = TaskTemplate.from_config(config)
        
        # Content will be None since it's not provided in config
        assert result.content is None
        assert result.priority == 2
        assert result.due_date_days_difference == 1

    def test_deeply_nested_children(self):
        """Test deeply nested children structure."""
        config = {
            'content': 'Level 0',
            'children': [
                {
                    'content': 'Level 1',
                    'children': [
                        {
                            'content': 'Level 2',
                            'children': [
                                {
                                    'content': 'Level 3',
                                }
                            ]
                        }
                    ]
                }
            ]
        }
        
        result = TaskTemplate.from_config(config)
        
        assert result.content == 'Level 0'
        level1 = result.children[0]
        assert level1.content == 'Level 1'
        level2 = level1.children[0]
        assert level2.content == 'Level 2'
        level3 = level2.children[0]
        assert level3.content == 'Level 3'
        assert level3.children == []


class TestTaskTemplateInit:
    """Tests for TaskTemplate initialization and defaults."""

    def test_default_values(self):
        """Test that __init__ applies correct defaults."""
        template = TaskTemplate(content='Test')
        
        assert template.content == 'Test'
        assert template.description is None
        assert template.due_date_days_difference == 0
        assert template.priority == 1
        assert template.children == []

    def test_children_defaults_to_empty_list(self):
        """Test that children defaults to empty list, not None."""
        template = TaskTemplate(content='Test', children=None)
        
        assert template.children == []
        assert template.children is not None

    def test_all_parameters_provided(self):
        """Test initialization with all parameters."""
        children = [TaskTemplate(content='Child')]
        template = TaskTemplate(
            content='Parent',
            description='Desc',
            due_date_days_difference=5,
            priority=3,
            children=children,
        )
        
        assert template.content == 'Parent'
        assert template.description == 'Desc'
        assert template.due_date_days_difference == 5
        assert template.priority == 3
        assert template.children == children
