"""
LLM integration for LangGraph module with Hugging Face support.
"""

from typing import Dict, Any, List, Optional, Union
import os
from abc import ABC, abstractmethod

from loguru import logger
from pydantic import BaseModel, Field

from .config import get_config
from .constants import ModelProviders, DefaultValues
from .prompts import build_task_generation_prompt, get_rule_based_response


class TaskGenerationOutput(BaseModel):
    """Pydantic model for structured task generation output."""
    main_task: str = Field(description="The main task title")
    description: str = Field(description="Detailed task description")
    urgency: str = Field(description="Task urgency level: low, medium, high")
    suggested_labels: List[str] = Field(description="List of suggested label names", default_factory=list)
    subtasks: List[str] = Field(description="List of subtask titles", default_factory=list)
    priority: Optional[int] = Field(description="Task priority (1-4)", default=None)


class BaseLLM(ABC):
    """Base class for LLM integrations."""
    
    @abstractmethod
    def generate_response(self, prompt: str, **kwargs) -> str:
        """Generate a response from the LLM."""
        pass
    
    @abstractmethod
    def is_available(self) -> bool:
        """Check if the LLM is available and configured."""
        pass


class HuggingFaceLLM(BaseLLM):
    """Hugging Face transformers integration with LangChain."""
    
    def __init__(self, config: Dict[str, Any]):
        """Initialize Hugging Face LLM."""
        self.config = config
        self.llm = None
        self.structured_llm = None
        self._initialize_model()
    
    def _initialize_model(self):
        """Initialize the Hugging Face LangChain LLM."""
        from langchain_huggingface import HuggingFacePipeline
        from transformers import pipeline
        
        model_name = self.config.get("model_name", DefaultValues.HUGGINGFACE_MODEL)
        
        logger.info(f"Initializing Hugging Face LangChain model: {model_name}")
        
        try:
            # Create transformers pipeline
            hf_pipeline = pipeline(
                "text-generation",
                model=model_name,
                max_length=self.config.get("max_length", DefaultValues.MAX_LENGTH),
                temperature=self.config.get("temperature", DefaultValues.TEMPERATURE),
                do_sample=self.config.get("do_sample", True),
                return_full_text=False
            )
            
            # Wrap in LangChain HuggingFace LLM
            self.llm = HuggingFacePipeline(pipeline=hf_pipeline)
            
            # Create structured LLM
            self.structured_llm = self.llm.with_structured_output(TaskGenerationOutput)
            
            logger.info("Hugging Face LangChain model initialized successfully")
            
        except Exception as e:
            logger.error(f"Error initializing Hugging Face model: {e}")
            self.llm = None
            self.structured_llm = None
    
    def generate_response(self, prompt: str, **kwargs) -> str:
        """Generate response using Hugging Face LangChain model."""
        if not self.is_available():
            raise RuntimeError("Hugging Face model not available")
        
        try:
            # Use LangChain LLM for generation
            response = self.llm.invoke(prompt)
            return response.strip() if response else ""
                
        except Exception as e:
            logger.error(f"Error generating response with Hugging Face: {e}")
            return ""
    
    def generate_structured_response(self, prompt: str, **kwargs) -> Optional[TaskGenerationOutput]:
        """Generate structured response using with_structured_output."""
        if not self.is_available() or self.structured_llm is None:
            logger.warning("Structured LLM not available, falling back to manual parsing")
            return None
        
        try:
            # Use structured output for better parsing
            result = self.structured_llm.invoke(prompt)
            return result
                
        except Exception as e:
            logger.error(f"Error generating structured response: {e}")
            return None
    
    def is_available(self) -> bool:
        """Check if Hugging Face model is available."""
        return self.llm is not None


class OpenAILLM(BaseLLM):
    """OpenAI API integration."""
    
    def __init__(self, config: Dict[str, Any]):
        """Initialize OpenAI LLM."""
        self.config = config
        self.client = None
        self._initialize_client()
    
    def _initialize_client(self):
        """Initialize OpenAI client."""
        import openai
        
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            logger.warning("OPENAI_API_KEY not found, OpenAI LLM disabled")
            return
        
        try:
            self.client = openai.OpenAI(api_key=api_key)
            logger.info("OpenAI client initialized successfully")
            
        except Exception as e:
            logger.error(f"Error initializing OpenAI client: {e}")
    
    def generate_response(self, prompt: str, **kwargs) -> str:
        """Generate response using OpenAI API."""
        if not self.is_available():
            raise RuntimeError("OpenAI client not available")
        
        try:
            model = self.config.get("model_name", "gpt-3.5-turbo")
            max_tokens = kwargs.get("max_tokens", self.config.get("max_tokens", 512))
            temperature = kwargs.get("temperature", self.config.get("temperature", 0.7))
            
            response = self.client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=max_tokens,
                temperature=temperature
            )
            
            return response.choices[0].message.content.strip()
            
        except Exception as e:
            logger.error(f"Error generating response with OpenAI: {e}")
            return ""
    
    def is_available(self) -> bool:
        """Check if OpenAI client is available."""
        return self.client is not None


class RuleBasedLLM(BaseLLM):
    """Fallback rule-based text generation."""
    
    def __init__(self, config: Dict[str, Any]):
        """Initialize rule-based LLM."""
        self.config = config
    
    def generate_response(self, prompt: str, **kwargs) -> str:
        """Generate response using rule-based logic."""
        return get_rule_based_response(prompt)
    
    def is_available(self) -> bool:
        """Rule-based LLM is always available."""
        return True


class LLMManager:
    """Manager for different LLM providers."""
    
    def __init__(self):
        """Initialize LLM manager."""
        self.config = get_config()
        self.llm = self._initialize_llm()
    
    def _initialize_llm(self) -> BaseLLM:
        """Initialize the configured LLM."""
        provider = self.config.get_model_provider()
        
        if provider == ModelProviders.HUGGINGFACE:
            llm = HuggingFaceLLM(self.config.get_huggingface_config())
            if llm.is_available():
                logger.info("Using Hugging Face LLM")
                return llm
        
        elif provider == ModelProviders.OPENAI:
            llm = OpenAILLM(self.config.get_openai_config())
            if llm.is_available():
                logger.info("Using OpenAI LLM")
                return llm
        
        # Fallback to rule-based generation
        if self.config.should_fallback_to_rules():
            logger.info("Using rule-based LLM fallback")
            return RuleBasedLLM({})
        else:
            raise RuntimeError(f"No available LLM for provider: {provider}")
    
    def generate_task_suggestions(
        self, 
        user_input: str, 
        available_labels: List[str],
        context: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        Generate task suggestions using the configured LLM.
        
        Args:
            user_input: User's natural language input
            available_labels: List of available labels from Todoist
            context: Additional context for generation
            
        Returns:
            Dictionary with task suggestions
        """
        context = context or {}
        
        # Build prompt for task generation
        prompt = self._build_task_generation_prompt(user_input, available_labels, context)
        
        try:
            # Try structured output first if available
            if hasattr(self.llm, 'generate_structured_response'):
                structured_result = self.llm.generate_structured_response(prompt)
                if structured_result:
                    return self._convert_structured_to_dict(structured_result)
            
            # Fallback to regular response and parsing
            response = self.llm.generate_response(prompt)
            return self._parse_llm_response(response, user_input)
            
        except Exception as e:
            logger.error(f"Error generating task suggestions: {e}")
            # Fallback to simple structure
            return self._fallback_task_generation(user_input, available_labels)
    
    def _build_task_generation_prompt(
        self, 
        user_input: str, 
        available_labels: List[str],
        context: Dict[str, Any]
    ) -> str:
        """Build prompt for task generation with structured output."""
        return build_task_generation_prompt(user_input, available_labels, context)
    
    def _convert_structured_to_dict(self, structured_output: TaskGenerationOutput) -> Dict[str, Any]:
        """Convert Pydantic model to dictionary format."""
        return {
            "main_task": structured_output.main_task,
            "description": structured_output.description,
            "urgency": structured_output.urgency,
            "suggested_labels": structured_output.suggested_labels,
            "subtasks": structured_output.subtasks,
            "priority": structured_output.priority
        }
    
    def _parse_llm_response(self, response: str, user_input: str) -> Dict[str, Any]:
        """Parse LLM response into structured task data."""
        # This is a simplified parser - in a real implementation,
        # you would use more sophisticated parsing or ask the LLM
        # to return structured data (JSON)
        
        return {
            "main_task": user_input,
            "description": f"Generated from: {user_input}",
            "urgency": "medium",
            "suggested_labels": ["auto_generated"],
            "subtasks": []
        }
    
    def _fallback_task_generation(
        self, 
        user_input: str, 
        available_labels: List[str]
    ) -> Dict[str, Any]:
        """Fallback task generation when LLM fails."""
        return {
            "main_task": user_input,
            "description": f"Task created from: {user_input}",
            "urgency": "medium",
            "suggested_labels": ["general"] if "general" in available_labels else [],
            "subtasks": []
        }
    
    def is_llm_available(self) -> bool:
        """Check if LLM is available."""
        return self.llm.is_available()
    
    def get_llm_info(self) -> Dict[str, Any]:
        """Get information about the current LLM."""
        return {
            "provider": self.config.get_model_provider(),
            "available": self.is_llm_available(),
            "fallback_enabled": self.config.should_fallback_to_rules()
        }