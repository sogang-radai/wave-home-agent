import logging
from typing import Optional, TypeVar

from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import BaseModel

from app.config import get_settings


logger = logging.getLogger(__name__)

ModelT = TypeVar("ModelT", bound=BaseModel)

_llm_cache: dict[str, ChatGoogleGenerativeAI] = {}


def get_llm(model: Optional[str] = None) -> Optional[ChatGoogleGenerativeAI]:
    """Returns a Gemini client for `model` (docs/api.md §1.1's per-request hint),
    or the configured default if omitted, or None if no API key is configured.

    Callers must treat None as "no LLM available" and fall back to rule-based
    generation, mirroring the WAVEHOME_CORE_API_MOCK fallback pattern. Clients
    are cached per model name so a per-request hint doesn't pay init cost twice.
    """
    settings = get_settings()
    if not settings.gemini_api_key:
        return None

    model_name = model or settings.gemini_model
    if model_name not in _llm_cache:
        _llm_cache[model_name] = ChatGoogleGenerativeAI(
            model=model_name,
            google_api_key=settings.gemini_api_key,
            timeout=settings.gemini_timeout_ms / 1000,
        )
    return _llm_cache[model_name]


async def invoke_structured(
    schema: type[ModelT],
    prompt: str,
    *,
    fallback: ModelT,
) -> ModelT:
    """Runs a structured-output LLM call with one retry, then falls back.

    Uses method="json_mode": ChatGoogleGenerativeAI's default
    "function_calling" mode only forces tool_choice for a hardcoded allowlist
    of model-name substrings that does not include gemini-3.1-flash-lite, so
    json_mode (Gemini's native response_schema) is used instead.
    """
    llm = get_llm()
    if llm is None:
        return fallback

    structured = llm.with_structured_output(schema, method="json_mode")
    for attempt in (1, 2):
        try:
            result = await structured.ainvoke(prompt)
            return result if isinstance(result, schema) else schema.model_validate(result)
        except Exception:
            logger.warning("LLM structured call failed (attempt %d/2)", attempt, exc_info=True)
            if attempt == 2:
                return fallback
    return fallback
