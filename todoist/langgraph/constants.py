"""
Constants for LangGraph module to avoid magic strings.
"""

class InputSources:
    """Constants for input source types."""
    ENV = "env"
    FILE = "file"
    MANUAL = "manual"


class TaskTypes:
    """Constants for task type classification."""
    GENERAL = "general_task"
    MEETING = "meeting_task"
    RESEARCH = "research_task"


class UrgencyLevels:
    """Constants for urgency levels."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class PriorityLevels:
    """Constants for priority mapping."""
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    URGENT = 4


class EnvironmentVariables:
    """Constants for environment variable names."""
    INPUT = "LANGGRAPH_INPUT"
    INPUT_FILE = "LANGGRAPH_INPUT_FILE"
    CLEAR_FILE_AFTER_READ = "LANGGRAPH_CLEAR_FILE_AFTER_READ"
    DEMO_INPUTS = "LANGGRAPH_DEMO_INPUTS"


class ModelProviders:
    """Constants for model provider names."""
    HUGGINGFACE = "huggingface"
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    LOCAL = "local"


class DefaultValues:
    """Default values for various components."""
    FREQUENCY_MINUTES = 1440  # 24 hours
    FILE_PATH = "langgraph_inputs.txt"
    HUGGINGFACE_MODEL = "microsoft/DialoGPT-medium"
    MAX_LENGTH = 512
    TEMPERATURE = 0.7
    
    # Urgency detection keywords
    URGENT_KEYWORDS = ["urgent", "asap", "immediately", "critical", "emergency"]
    COMPLEX_KEYWORDS = ["project", "complex", "multiple", "comprehensive"]
    MEETING_KEYWORDS = ["meeting", "call", "presentation", "conference", "interview"]
    RESEARCH_KEYWORDS = ["research", "study", "learn", "analyze", "investigate"]


class ValidationLimits:
    """Constants for validation limits."""
    MIN_CONTENT_LENGTH = 3
    MAX_WORD_COUNT_SIMPLE = 5
    MIN_PRIORITY = 1
    MAX_PRIORITY = 4