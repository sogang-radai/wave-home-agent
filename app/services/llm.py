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


def _extract_text(content: object) -> str:
    """Gemini 3.x returns AIMessage.content as a list of content blocks (text +
    thought-signature 'extras', not a plain string like older models). Concatenates
    just the text blocks; falls back to str() for any other shape."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
        return "".join(parts)
    return str(content)


async def invoke_text(
    prompt: str,
    *,
    fallback: str,
    model: Optional[str] = None,
) -> tuple[str, str]:
    """Plain-text counterpart to invoke_structured, for docs/api.md §1.4's
    summaryText/reportText generation. Returns (text, model_name_used); model_name_used
    is "rule-based" whenever the fallback was used (no LLM configured, or both attempts
    failed), so callers can surface that honestly in their response's `model` field."""
    llm = get_llm(model)
    if llm is None:
        return fallback, "rule-based"

    for attempt in (1, 2):
        try:
            result = await llm.ainvoke(prompt)
            text = _extract_text(result.content).strip()
            if not text:
                raise ValueError("LLM returned empty text content")
            return text, model or get_settings().gemini_model
        except Exception:
            logger.warning("LLM text call failed (attempt %d/2)", attempt, exc_info=True)
            if attempt == 2:
                return fallback, "rule-based"
    return fallback, "rule-based"


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
