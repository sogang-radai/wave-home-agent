from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "WaveHome Agent Server"
    app_env: str = "local"

    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.1-flash-lite"
    gemini_timeout_ms: int = 20000

    wavehome_core_api_base_url: str = "http://127.0.0.1:9000"
    wavehome_core_api_timeout_ms: int = 5000
    wavehome_core_api_mock: bool = Field(
        default=True,
        description="Use placeholder data until the C++ server API is ready.",
    )

    # docs/api.md §2's outbound tools (db.query, devices, routine-tasks, rag.search) target the
    # C++ backend's /internal/v1/* namespace, distinct from the legacy tools above which predate
    # that contract. Kept separate so upgrading one doesn't move the other's base URL.
    wavehome_agent_internal_base_url: str = "http://127.0.0.1:8500/internal/v1"

    # Ollama server (OpenAI-compatible /v1/*) that docs/api.md §1.3's /llm/v1/* proxy forwards to.
    # Serves both chat models (gemma*) and the nomic-embed-text embedding model. Real address is
    # set via .env only (not committed) — this default is just for local dev with a local Ollama.
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_timeout_ms: int = 30000

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
