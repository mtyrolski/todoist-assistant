"""
Label management for intelligent label assignment based on existing Todoist labels.
"""

from typing import List, Dict, Set, Optional
import re
from collections import defaultdict

try:
    from loguru import logger
except ImportError:
    import logging
    logger = logging.getLogger(__name__)

from todoist.database.db_labels import DatabaseLabels


class LabelManager:
    """Manages label assignment based on existing Todoist labels."""
    
    def __init__(self):
        """Initialize label manager."""
        self.db_labels = DatabaseLabels()
        self.available_labels: List[str] = []
        self.label_categories: Dict[str, List[str]] = {}
        self._load_labels()
    
    def _load_labels(self):
        """Load labels from Todoist database."""
        try:
            # Reset and fetch fresh label data
            self.db_labels.reset()
            
            # Get available labels from the database
            if hasattr(self.db_labels, '_labels') and self.db_labels._labels:
                self.available_labels = [label.get('name', '') for label in self.db_labels._labels if label.get('name')]
            else:
                self.available_labels = []
            
            logger.info(f"Loaded {len(self.available_labels)} labels from Todoist")
            
            # Categorize labels for intelligent assignment
            self._categorize_labels()
            
        except Exception as e:
            logger.error(f"Error loading labels from Todoist: {e}")
            self.available_labels = []
            self.label_categories = {}
    
    def _categorize_labels(self):
        """Categorize labels by common patterns for intelligent assignment."""
        self.label_categories = {
            'meeting': [],
            'work': [],
            'personal': [],
            'urgent': [],
            'project': [],
            'research': [],
            'communication': [],
            'planning': [],
            'general': []
        }
        
        # Pattern matching for label categorization
        patterns = {
            'meeting': [r'meet', r'call', r'conference', r'presentation', r'discussion'],
            'work': [r'work', r'job', r'office', r'business', r'professional'],
            'personal': [r'personal', r'home', r'family', r'life'],
            'urgent': [r'urgent', r'asap', r'immediate', r'critical', r'priority'],
            'project': [r'project', r'dev', r'build', r'create'],
            'research': [r'research', r'study', r'learn', r'investigate', r'analyze'],
            'communication': [r'email', r'message', r'contact', r'reach', r'send'],
            'planning': [r'plan', r'organize', r'schedule', r'prepare', r'setup']
        }
        
        for label in self.available_labels:
            label_lower = label.lower()
            categorized = False
            
            for category, pattern_list in patterns.items():
                for pattern in pattern_list:
                    if re.search(pattern, label_lower):
                        self.label_categories[category].append(label)
                        categorized = True
                        break
                if categorized:
                    break
            
            # If not categorized, add to general
            if not categorized:
                self.label_categories['general'].append(label)
        
        logger.debug(f"Categorized labels: {dict(self.label_categories)}")
    
    def get_available_labels(self) -> List[str]:
        """Get list of all available labels."""
        return self.available_labels.copy()
    
    def suggest_labels_for_task(self, content: str, task_type: str = "general") -> List[str]:
        """
        Suggest appropriate labels for a task based on content and type.
        
        Args:
            content: Task content to analyze
            task_type: Type of task (meeting, research, general, etc.)
            
        Returns:
            List of suggested label names
        """
        if not self.available_labels:
            logger.warning("No labels available from Todoist")
            return []
        
        suggested_labels = set()
        content_lower = content.lower()
        
        # 1. Start with task type-based suggestions
        if task_type in self.label_categories:
            suggested_labels.update(self.label_categories[task_type][:2])  # Top 2 from category
        
        # 2. Content-based label matching
        content_suggestions = self._match_labels_by_content(content_lower)
        suggested_labels.update(content_suggestions[:3])  # Top 3 content matches
        
        # 3. If still no labels, add some general ones
        if not suggested_labels and self.label_categories['general']:
            suggested_labels.add(self.label_categories['general'][0])
        
        # Convert to list and limit to reasonable number
        result = list(suggested_labels)[:5]  # Max 5 labels
        
        logger.debug(f"Suggested labels for '{content}': {result}")
        return result
    
    def _match_labels_by_content(self, content_lower: str) -> List[str]:
        """Match labels based on content analysis."""
        matched_labels = []
        
        for label in self.available_labels:
            label_lower = label.lower()
            
            # Direct substring match
            if label_lower in content_lower or content_lower in label_lower:
                matched_labels.append(label)
                continue
            
            # Word-based matching
            label_words = re.findall(r'\w+', label_lower)
            content_words = re.findall(r'\w+', content_lower)
            
            # Check for common words
            if any(word in content_words for word in label_words if len(word) > 2):
                matched_labels.append(label)
        
        # Sort by relevance (shorter labels that match are more relevant)
        matched_labels.sort(key=len)
        return matched_labels
    
    def validate_labels(self, labels: List[str]) -> List[str]:
        """
        Validate that labels exist in Todoist and return only valid ones.
        
        Args:
            labels: List of label names to validate
            
        Returns:
            List of valid label names
        """
        if not labels:
            return []
        
        valid_labels = []
        for label in labels:
            if label in self.available_labels:
                valid_labels.append(label)
            else:
                logger.warning(f"Label '{label}' not found in Todoist labels")
        
        return valid_labels
    
    def get_label_suggestions_by_urgency(self, urgency: str) -> List[str]:
        """Get label suggestions based on urgency level."""
        if urgency == "high" and self.label_categories['urgent']:
            return self.label_categories['urgent'][:2]
        elif urgency == "medium" and self.label_categories['general']:
            return self.label_categories['general'][:1]
        return []
    
    def get_label_stats(self) -> Dict[str, int]:
        """Get statistics about available labels."""
        stats = {
            'total_labels': len(self.available_labels),
            'categories': {cat: len(labels) for cat, labels in self.label_categories.items()}
        }
        return stats
    
    def refresh_labels(self):
        """Refresh labels from Todoist."""
        logger.info("Refreshing labels from Todoist")
        self._load_labels()
    
    def find_labels_by_pattern(self, pattern: str) -> List[str]:
        """Find labels matching a specific pattern."""
        matching_labels = []
        try:
            regex = re.compile(pattern, re.IGNORECASE)
            for label in self.available_labels:
                if regex.search(label):
                    matching_labels.append(label)
        except re.error:
            logger.error(f"Invalid regex pattern: {pattern}")
        
        return matching_labels
    
    def get_most_common_labels(self, limit: int = 10) -> List[str]:
        """
        Get most commonly used labels (based on simple heuristics).
        
        This is a placeholder - in a real implementation, you might track
        label usage frequency from the database.
        """
        # For now, return labels from multiple categories
        common_labels = []
        
        # Add one from each category
        for category, labels in self.label_categories.items():
            if labels and len(common_labels) < limit:
                common_labels.append(labels[0])
        
        return common_labels[:limit]