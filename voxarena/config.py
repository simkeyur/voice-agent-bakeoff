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

# Determine if we are running in the git repo dev environment or a packaged install
current_dir = os.path.dirname(os.path.abspath(__file__))
repo_root = os.path.abspath(os.path.join(current_dir, ".."))

is_dev_mode = (
    os.path.exists(os.path.join(repo_root, "pyproject.toml")) and 
    os.path.exists(os.path.join(repo_root, "ui"))
)

default_base_dir = os.environ.get("BASE_DIR") or (repo_root if is_dev_mode else os.getcwd())


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
    EVALUATION_MODEL: str = "gemini-3.1-flash-lite"
    EVALUATION_PROVIDER: str = "gemini"

    # TTS configuration for synthesizing user-utterance audio.
    # Engine: "auto" follows the fallback chain (openai > google > local). Explicit
    # choices force that engine — they still fall back if unavailable, but try the
    # preferred one first.
    TTS_ENGINE: Literal["auto", "openai", "google", "local"] = "local"
    OPENAI_TTS_MODEL: str = "tts-1"
    OPENAI_TTS_VOICE: str = "nova"
    GOOGLE_TTS_VOICE: str = "en-US-Journey-F"
    
    # Directory paths
    BASE_DIR: str = default_base_dir
    RESULTS_DIR: str = ""
    SCRIPT_DIR: str = ""
    AUDIO_DIR: str = ""
    REVIEW_DIR: str = ""

    def __init__(self, **values):
        super().__init__(**values)
        if not self.RESULTS_DIR:
            self.RESULTS_DIR = os.path.join(self.BASE_DIR, "results")
        if not self.SCRIPT_DIR:
            self.SCRIPT_DIR = os.path.join(self.BASE_DIR, "script")
        if not self.AUDIO_DIR:
            self.AUDIO_DIR = os.path.join(self.SCRIPT_DIR, "audio")
        if not self.REVIEW_DIR:
            self.REVIEW_DIR = os.path.join(self.BASE_DIR, "review")


# Global settings instance
settings = AppSettings()

# Ensure directories exist
for directory in [settings.RESULTS_DIR, settings.SCRIPT_DIR, settings.AUDIO_DIR, settings.REVIEW_DIR]:
    os.makedirs(directory, exist_ok=True)

# Bootstrap default scripts if in packaged mode and utterances.yaml is missing
utterances_file = os.path.join(settings.SCRIPT_DIR, "utterances.yaml")
if not is_dev_mode and not os.path.exists(utterances_file):
    try:
        import importlib.resources
        import shutil

        src_path = importlib.resources.files("voxarena").joinpath("default_script")
        if src_path.exists():
            for item in src_path.iterdir():
                dest_item = os.path.join(settings.SCRIPT_DIR, item.name)
                if item.is_dir():
                    shutil.copytree(str(item), dest_item, dirs_exist_ok=True)
                else:
                    shutil.copy2(str(item), dest_item)
    except Exception as e:
        print(f"Warning: failed to bootstrap default script files: {e}")


def get_setting(key: str) -> Optional[str]:
    # 1. Environment variable wins
    if key in os.environ:
        return os.environ[key]
        
    # 2. SQLite settings table
    try:
        from voxarena.database import get_db_connection, DB_PATH
        if os.path.exists(DB_PATH):
            with get_db_connection() as conn:
                row = conn.execute("SELECT value FROM settings WHERE key = ?;", (key,)).fetchone()
                if row:
                    return row[0]
    except Exception:
        pass

    # 3. Fallback to AppSettings memory/env file
    return getattr(settings, key, None)


def set_setting(key: str, value: str) -> None:
    # 1. Update SQLite settings table
    try:
        from voxarena.database import get_db_connection, _ensure_initialized
        _ensure_initialized()
        with get_db_connection() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?);",
                (key, value)
            )
            conn.commit()
    except Exception as e:
        print(f"Warning: failed to write setting {key} to database: {e}")

    # 2. Update memory settings if class field
    if hasattr(settings, key):
        setattr(settings, key, value)

    # 3. Update environment variable
    os.environ[key] = value
