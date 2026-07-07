import logging
from typing import Optional

from app.clients.ollama import OllamaClient, OllamaError
from app.config import get_settings


logger = logging.getLogger(__name__)


class EmbeddingError(Exception):
    """Raised when generating an embedding via Ollama fails. Callers (job runners in
    app/services/{sleep,power}_analysis.py) map is_timeout onto GENERATION_TIMEOUT,
    otherwise GENERATION_FAILED (docs/api.md §1.4)."""

    def __init__(self, message: str, *, is_timeout: bool = False) -> None:
        super().__init__(message)
        self.is_timeout = is_timeout


async def generate_embedding(text: str, model: Optional[str] = None) -> tuple[list[float], str]:
    settings = get_settings()
    model_name = model or settings.default_embedding_model
    client = OllamaClient(settings)
    logger.info("embedding request: model=%s ollama=%s text_len=%d", model_name, settings.ollama_base_url, len(text))
    try:
        response = await client.post("/v1/embeddings", {"model": model_name, "input": text})
    except OllamaError as exc:
        logger.warning("embedding request failed: model=%s error=%s", model_name, exc)
        raise EmbeddingError(str(exc), is_timeout=exc.is_timeout) from exc

    try:
        embedding = response["data"][0]["embedding"]
    except (KeyError, IndexError) as exc:
        raise EmbeddingError(f"unexpected embeddings response shape: {response}") from exc

    logger.info("embedding received: model=%s dims=%d first_values=%s", model_name, len(embedding), embedding[:3])
    return embedding, model_name
