import logging
from typing import Optional, TypeVar

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.runnables import RunnableConfig
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI
from pydantic import BaseModel

from app.config import get_settings


logger = logging.getLogger(__name__)

ModelT = TypeVar("ModelT", bound=BaseModel)

_llm_cache: dict[str, BaseChatModel] = {}


def _provider() -> str:
    return get_settings().llm_provider.strip().lower()


def default_model_name() -> str:
    """Returns the currently configured provider's default model name, for
    surfacing in response `model` fields without hardcoding a provider."""
    settings = get_settings()
    provider = _provider()
    if provider == "openai":
        return settings.openai_model
    if provider == "ollama":
        return settings.ollama_chat_model
    return settings.gemini_model


def _structured_method(provider: str) -> str:
    """Gemini's with_structured_output default ("function_calling") only forces
    tool_choice for a hardcoded allowlist of model-name substrings that does not
    include gemini-3.1-flash-lite, so json_mode (Gemini's native response_schema)
    is used instead. OpenAI's function_calling mode has no such gap and is the
    more reliable choice there.

    Ollama-served models are grouped with Gemini here too: whether tool_choice
    forcing works reliably through Ollama's OpenAI-compat layer depends on the
    served model/version, so json_mode (plain JSON-schema prompting) is the
    safer default until a specific served model is verified to support it."""
    return "function_calling" if provider == "openai" else "json_mode"


def get_llm(model: Optional[str] = None) -> Optional[BaseChatModel]:
    """Returns a chat model client for `model` (docs/api.md §1.1's per-request
    hint), or the configured default if omitted, or None if no API key is
    configured. The provider (Gemini, OpenAI, or Ollama-served Gemma) is
    selected by LLM_PROVIDER.

    Callers must treat None as "no LLM available" and fall back to rule-based
    generation, mirroring the WAVEHOME_CORE_API_MOCK fallback pattern. Clients
    are cached per (provider, model name) so a per-request hint or a provider
    switch doesn't pay init cost twice or collide with a stale cache entry.
    """
    settings = get_settings()
    provider = _provider()

    if provider == "openai":
        api_key = settings.openai_api_key
        default_model = settings.openai_model
        timeout_ms = settings.openai_timeout_ms
    elif provider == "ollama":
        # Ollama doesn't validate this key, but langchain_openai rejects an
        # empty one - app/clients/ollama.py's OLLAMA_BASE_URL is the same
        # server, just addressed at its OpenAI-compat /v1 path here instead
        # of proxied through app/routers/llm.py.
        api_key = settings.ollama_api_key
        default_model = settings.ollama_chat_model
        timeout_ms = settings.ollama_timeout_ms
    else:
        api_key = settings.gemini_api_key
        default_model = settings.gemini_model
        timeout_ms = settings.gemini_timeout_ms

    if not api_key:
        return None

    model_name = model or default_model
    cache_key = f"{provider}:{model_name}"
    if cache_key not in _llm_cache:
        if provider == "openai":
            _llm_cache[cache_key] = ChatOpenAI(
                model=model_name,
                api_key=api_key,
                timeout=timeout_ms / 1000,
            )
        elif provider == "ollama":
            # max_retries=0: ChatOpenAI's own default (2) would silently repeat a
            # full `timeout`-length wait on top of invoke_text/invoke_structured's
            # own 2-attempt retry, so a slow/overloaded model could take up to
            # timeout * 3 * 2 before falling back instead of the intended timeout * 2.
            _llm_cache[cache_key] = ChatOpenAI(
                model=model_name,
                api_key=api_key,
                base_url=f"{settings.ollama_base_url.rstrip('/')}/v1",
                timeout=timeout_ms / 1000,
                max_retries=0,
            )
        else:
            _llm_cache[cache_key] = ChatGoogleGenerativeAI(
                model=model_name,
                google_api_key=api_key,
                timeout=timeout_ms / 1000,
            )
    return _llm_cache[cache_key]


def _extract_text(content: object) -> str:
    """Gemini 3.x returns AIMessage.content as a list of content blocks (text +
    thought-signature 'extras', not a plain string like older models); OpenAI
    returns a plain string, handled by the isinstance(content, str) branch.
    Concatenates just the text blocks; falls back to str() for any other shape."""
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
            return text, model or default_model_name()
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
    config: Optional[RunnableConfig] = None,
) -> ModelT:
    """Runs a structured-output LLM call with one retry, then falls back.

    The structured-output method (json_mode vs function_calling) is chosen per
    provider by _structured_method, since Gemini and OpenAI have different
    reliability quirks around with_structured_output's default mode.

    `config` is forwarded to the underlying call so callers running inside a
    LangGraph node can tag it (e.g. app/graph/turn_graph.py tags its domain
    classification call as background so it never gets treated as the
    turn's visible answer in chat_runtime.py's SSE stream).
    """
    llm = get_llm()
    if llm is None:
        return fallback

    structured = llm.with_structured_output(schema, method=_structured_method(_provider()))
    for attempt in (1, 2):
        try:
            result = await structured.ainvoke(prompt, config=config)
            return result if isinstance(result, schema) else schema.model_validate(result)
        except Exception:
            logger.warning("LLM structured call failed (attempt %d/2)", attempt, exc_info=True)
            if attempt == 2:
                return fallback
    return fallback
