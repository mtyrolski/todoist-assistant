"""
Configuration management for LangGraph module using Hydra.
"""

import os
from typing import Dict, Any, Optional

try:
    from omegaconf import DictConfig, OmegaConf
    OMEGACONF_AVAILABLE = True
except ImportError:
    OMEGACONF_AVAILABLE = False
    DictConfig = dict
    OmegaConf = None

try:
    from loguru import logger
except ImportError:
    import logging
    logger = logging.getLogger(__name__)

from .constants import ModelProviders, DefaultValues


class LangGraphConfig:
    """Configuration manager for LangGraph module."""
    
    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize configuration manager.
        
        Args:
            config_path: Path to configuration file. If None, uses default.
        """
        self.config_path = config_path or self._get_default_config_path()
        self.config = self._load_config()
    
    def _get_default_config_path(self) -> str:
        """Get default configuration file path."""
        return os.path.join(
            os.path.dirname(__file__), 
            "..", "..", "configs", "langgraph", "model.yaml"
        )
    
    def _load_config(self) -> DictConfig:
        """Load configuration from file."""
        try:
            if OMEGACONF_AVAILABLE and os.path.exists(self.config_path):
                config = OmegaConf.load(self.config_path)
                logger.info(f"Loaded LangGraph configuration from {self.config_path}")
                return config
            else:
                if not OMEGACONF_AVAILABLE:
                    logger.warning("OmegaConf not available, using default configuration")
                else:
                    logger.warning(f"Configuration file not found: {self.config_path}")
                return self._get_default_config()
                
        except Exception as e:
            logger.error(f"Error loading configuration: {e}")
            return self._get_default_config()
    
    def _get_default_config(self) -> DictConfig:
        """Get default configuration when file is not available."""
        default_config = {
            "model": {
                "provider": ModelProviders.HUGGINGFACE,
                "fallback_to_rules": True,
                "huggingface": {
                    "model_name": DefaultValues.HUGGINGFACE_MODEL,
                    "max_length": DefaultValues.MAX_LENGTH,
                    "temperature": DefaultValues.TEMPERATURE,
                    "device": "auto"
                }
            },
            "constants": {
                "urgency_levels": {
                    "LOW": "low",
                    "MEDIUM": "medium", 
                    "HIGH": "high"
                },
                "priority_mapping": {
                    "low": 1,
                    "medium": 2,
                    "high": 3,
                    "urgent": 4
                }
            }
        }
        
        logger.info("Using default LangGraph configuration")
        if OMEGACONF_AVAILABLE:
            return OmegaConf.create(default_config)
        else:
            return default_config
    
    def get_model_config(self) -> Dict[str, Any]:
        """Get model configuration."""
        if OMEGACONF_AVAILABLE:
            return OmegaConf.to_container(self.config.model, resolve=True)
        else:
            return self.config.get("model", {})
    
    def get_model_provider(self) -> str:
        """Get configured model provider."""
        model_config = self.config.get("model", {}) if isinstance(self.config, dict) else self.config.model
        return model_config.get("provider", ModelProviders.HUGGINGFACE)
    
    def get_huggingface_config(self) -> Dict[str, Any]:
        """Get Hugging Face model configuration."""
        if OMEGACONF_AVAILABLE:
            return OmegaConf.to_container(
                self.config.model.get("huggingface", {}), 
                resolve=True
            )
        else:
            return self.config.get("model", {}).get("huggingface", {})
    
    def get_openai_config(self) -> Dict[str, Any]:
        """Get OpenAI model configuration."""
        if OMEGACONF_AVAILABLE:
            return OmegaConf.to_container(
                self.config.model.get("openai", {}), 
                resolve=True
            )
        else:
            return self.config.get("model", {}).get("openai", {})
    
    def should_fallback_to_rules(self) -> bool:
        """Check if should fallback to rule-based generation."""
        model_config = self.config.get("model", {}) if isinstance(self.config, dict) else self.config.model
        return model_config.get("fallback_to_rules", True)
    
    def get_prompts(self) -> Dict[str, str]:
        """Get configured prompts."""
        if OMEGACONF_AVAILABLE:
            return OmegaConf.to_container(
                self.config.get("prompts", {}), 
                resolve=True
            )
        else:
            return self.config.get("prompts", {})
    
    def get_constants(self) -> Dict[str, Any]:
        """Get constants from configuration."""
        if OMEGACONF_AVAILABLE:
            return OmegaConf.to_container(
                self.config.get("constants", {}), 
                resolve=True
            )
        else:
            return self.config.get("constants", {})
    
    def get_priority_mapping(self) -> Dict[str, int]:
        """Get priority level mapping."""
        constants = self.get_constants()
        return constants.get("priority_mapping", {
            "low": 1,
            "medium": 2, 
            "high": 3,
            "urgent": 4
        })


# Global configuration instance
_config_instance: Optional[LangGraphConfig] = None


def get_config() -> LangGraphConfig:
    """Get global configuration instance."""
    global _config_instance
    if _config_instance is None:
        _config_instance = LangGraphConfig()
    return _config_instance


def reload_config(config_path: Optional[str] = None) -> LangGraphConfig:
    """Reload configuration from file."""
    global _config_instance
    _config_instance = LangGraphConfig(config_path)
    return _config_instance