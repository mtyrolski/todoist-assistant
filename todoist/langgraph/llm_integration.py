"""
LLM integration for LangGraph module with Hugging Face support.
"""

from typing import Dict, Any, List, Optional, Union
import os
from abc import ABC, abstractmethod

try:
    from loguru import logger
except ImportError:
    import logging
    logger = logging.getLogger(__name__)

from .config import get_config
from .constants import ModelProviders, DefaultValues


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
    """Hugging Face transformers integration."""
    
    def __init__(self, config: Dict[str, Any]):
        """Initialize Hugging Face LLM."""
        self.config = config
        self.model = None
        self.tokenizer = None
        self._initialize_model()
    
    def _initialize_model(self):
        """Initialize the Hugging Face model and tokenizer."""
        try:
            from transformers import AutoModelForCausalLM, AutoTokenizer, pipeline
            
            model_name = self.config.get("model_name", DefaultValues.HUGGINGFACE_MODEL)
            device = self.config.get("device", "auto")
            
            logger.info(f"Initializing Hugging Face model: {model_name}")
            
            # Use pipeline for simpler text generation
            self.pipeline = pipeline(
                "text-generation",
                model=model_name,
                device=0 if device == "cuda" else -1,  # 0 for GPU, -1 for CPU
                return_full_text=False,
                max_length=self.config.get("max_length", DefaultValues.MAX_LENGTH),
                temperature=self.config.get("temperature", DefaultValues.TEMPERATURE),
                do_sample=self.config.get("do_sample", True),
                top_p=self.config.get("top_p", 0.9)
            )
            
            logger.info("Hugging Face model initialized successfully")
            
        except ImportError:
            logger.warning("Transformers library not available, HuggingFace LLM disabled")
            self.pipeline = None
        except Exception as e:
            logger.error(f"Error initializing Hugging Face model: {e}")
            self.pipeline = None
    
    def generate_response(self, prompt: str, **kwargs) -> str:
        """Generate response using Hugging Face model."""
        if not self.is_available():
            raise RuntimeError("Hugging Face model not available")
        
        try:
            max_length = kwargs.get("max_length", self.config.get("max_length", DefaultValues.MAX_LENGTH))
            
            # Generate response
            result = self.pipeline(
                prompt,
                max_length=max_length,
                num_return_sequences=1,
                pad_token_id=self.pipeline.tokenizer.eos_token_id
            )
            
            if result and len(result) > 0:
                return result[0]["generated_text"].strip()
            else:
                return ""
                
        except Exception as e:
            logger.error(f"Error generating response with Hugging Face: {e}")
            return ""
    
    def is_available(self) -> bool:
        """Check if Hugging Face model is available."""
        return self.pipeline is not None


class OpenAILLM(BaseLLM):
    """OpenAI API integration."""
    
    def __init__(self, config: Dict[str, Any]):
        """Initialize OpenAI LLM."""
        self.config = config
        self.client = None
        self._initialize_client()
    
    def _initialize_client(self):
        """Initialize OpenAI client."""
        try:
            import openai
            
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                logger.warning("OPENAI_API_KEY not found, OpenAI LLM disabled")
                return
            
            self.client = openai.OpenAI(api_key=api_key)
            logger.info("OpenAI client initialized successfully")
            
        except ImportError:
            logger.warning("OpenAI library not available, OpenAI LLM disabled")
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
        # This is a simple fallback that returns a structured response
        # In a real implementation, this could use templates or basic NLP
        
        if "generate task" in prompt.lower():
            return "Generated task based on input with appropriate subtasks."
        elif "suggest labels" in prompt.lower():
            return "Suggested labels: general, planning, action"
        else:
            return "Task processed using rule-based generation."
    
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
        """Build prompt for task generation."""
        prompts = self.config.get_prompts()
        
        system_prompt = prompts.get("system_prompt", "Generate structured tasks.")
        task_prompt = prompts.get("task_generation_prompt", 
            "Based on the user input: '{user_input}', generate appropriate tasks.")
        
        # Format the prompt with available data
        formatted_prompt = task_prompt.format(
            user_input=user_input,
            available_labels=", ".join(available_labels) if available_labels else "none"
        )
        
        return f"{system_prompt}\n\n{formatted_prompt}"
    
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