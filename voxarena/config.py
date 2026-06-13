import os
from typing import Literal, Optional
from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

class ProviderConfig(BaseModel):
    provider: str = "gemini"
    model: str = "gemini-3.1-flash-live-preview"  # Concrete default model (voice/live)
    transport: Literal["direct-injection", "webrtc-local"] = "direct-injection"

    @field_validator("provider")
    @classmethod
    def _validate_provider(cls, v: str) -> str:
        # Lazy import to avoid circular dependency (providers -> base -> ... -> config)
        from voxarena.providers import provider_names
        names = provider_names()
        if v not in names:
            raise ValueError(f"Unknown provider '{v}'. Registered: {names}")
        return v
    run_id: Optional[str] = None
    prompt_version: str = "v1.0"
    tool_schema_version: str = "v1.0"
    temperature: float = Field(0.0, ge=0.0, le=2.0)
    max_tokens: Optional[int] = None

class AppSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )
    
    # Port for the FastAPI server
    PORT: int = 8000
    
    # API Keys
    GOOGLE_API_KEY: Optional[str] = None
    OPENAI_API_KEY: Optional[str] = None
    
    # Voice agent models (must be live/realtime-capable)
    GEMINI_MODEL: str = "gemini-3.1-flash-live-preview"
    OPENAI_MODEL: str = "gpt-realtime-2"
    GEMINI_EVAL_MODEL: str = "gemini-3.1-flash-lite"
    OPENAI_EVAL_MODEL: str = "gpt-5.4-mini"
    
    # Directory paths (relative to workspace root)
    BASE_DIR: str = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    RESULTS_DIR: str = os.path.join(BASE_DIR, "results")
    SCRIPT_DIR: str = os.path.join(BASE_DIR, "script")
    AUDIO_DIR: str = os.path.join(SCRIPT_DIR, "audio")
    REVIEW_DIR: str = os.path.join(BASE_DIR, "review")

# Global settings instance
settings = AppSettings()

# Ensure directories exist
for directory in [settings.RESULTS_DIR, settings.SCRIPT_DIR, settings.AUDIO_DIR, settings.REVIEW_DIR]:
    os.makedirs(directory, exist_ok=True)
