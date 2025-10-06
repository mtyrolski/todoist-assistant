"""
Configuration settings for the LangGraph + Chainlit chat application.
"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    model_config = SettingsConfigDict(
        env_file='.env',
        env_file_encoding='utf-8',
        case_sensitive=False,
        extra='ignore'
    )
    
    HUGGINGFACEHUB_API_TOKEN: str | None = None
    HF_MODEL_ID: str = "HuggingFaceH4/zephyr-7b-beta"
    EVENTS_PATH: str = ".data/events.json"
    MAX_TOOL_ITERS: int = 2


def get_settings() -> Settings:
    """Get application settings singleton."""
    return Settings()
