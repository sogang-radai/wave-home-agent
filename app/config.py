from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "WaveHome Agent Server"
    app_env: str = "local"

    llm_provider: str = "gemini"  # "gemini" | "openai"

    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.1-flash-lite"
    gemini_timeout_ms: int = 20000

    openai_api_key: str = ""
    openai_model: str = "gpt-5.4-nano"
    openai_timeout_ms: int = 20000

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

    # device-tool-api.md의 카메라 stream GET/PUT 응답 url은 실 백엔드에서만 유의미(go2rtc가
    # 내려주는 WebRTC/MJPEG URI). mock 모드에서 스트리밍 중일 때 채워 넣을 placeholder만 여기서
    # 설정으로 뺀다 — 로컬에서 실제 재생 가능한 URL로 임시로 바꿔보고 싶을 때 코드 수정 없이
    # .env만 바꾸면 되도록.
    mock_camera_stream_url: str = "mock://stream"

    # Ollama server (OpenAI-compatible /v1/*) that docs/api.md §1.3's /llm/v1/* proxy forwards to.
    # Serves both chat models (gemma*) and the nomic-embed-text embedding model. Real address is
    # set via .env only (not committed) — this default is just for local dev with a local Ollama.
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_timeout_ms: int = 30000

    # docs/api.md §1.4's default embedding model for /sleep/v1 and /power/v1 job
    # responses, matching the vec_* schema dimension (nomic-embed-text, 768).
    default_embedding_model: str = "nomic-embed-text"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
