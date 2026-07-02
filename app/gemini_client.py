from __future__ import annotations

import httpx
from google import genai
from google.genai import errors as genai_errors
from google.genai import types

from app.config import GEMINI_API_KEY, GEMINI_MODEL, GEMINI_TIMEOUT_MS
from app.errors import ApiError

SYSTEM_PROMPT = """너는 WaveHome이라는 스마트홈 서비스의 AI 어시스턴트 'WaveAI'다.
사용자의 수면, 자세, 심박 데이터를 바탕으로 친절하고 구체적인 한국어 답변을 준다.
데이터가 없는 항목은 추측해서 단정하지 말고, 안내 위주로 답한다.
답변은 2~4문장 정도로 간결하게 작성한다.

[활성 구성원의 최근 데이터]
{context}
"""

_client: genai.Client | None = None


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(api_key=GEMINI_API_KEY)
    return _client


def _to_content(role: str, text: str) -> types.Content:
    gemini_role = "model" if role == "assistant" else "user"
    return types.Content(role=gemini_role, parts=[types.Part(text=text)])


def generate_reply(
    context: str,
    user_text: str,
    history: list[tuple[str, str]] | None = None,
) -> str:
    contents = [_to_content(role, text) for role, text in (history or [])]
    contents.append(_to_content("user", user_text))

    config = types.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT.format(context=context),
        http_options=types.HttpOptions(timeout=GEMINI_TIMEOUT_MS),
    )

    try:
        response = _get_client().models.generate_content(
            model=GEMINI_MODEL,
            contents=contents,
            config=config,
        )
    except httpx.TimeoutException as exc:
        raise ApiError(504, "AI_TIMEOUT", "AI 응답 생성 시간이 초과되었습니다.") from exc
    except genai_errors.APIError as exc:
        raise ApiError(
            502, "AI_PROVIDER_ERROR", "AI 응답을 생성하지 못했습니다. 잠시 후 다시 시도해주세요."
        ) from exc
    except Exception as exc:  # noqa: BLE001 - unknown SDK/network failure, surface as provider error
        raise ApiError(
            502, "AI_PROVIDER_ERROR", "AI 응답을 생성하지 못했습니다. 잠시 후 다시 시도해주세요."
        ) from exc

    text = (response.text or "").strip()
    if not text:
        raise ApiError(
            502, "AI_PROVIDER_ERROR", "AI 응답을 생성하지 못했습니다. 잠시 후 다시 시도해주세요."
        )
    return text
