"""Classifies a chat turn into a tool domain so app/graph/turn_graph.py can
dispatch to a subgraph exposing only that domain's tools, instead of one
general agent choosing from every tool every turn (docs/agent_architecture.md's
"Legacy Domain Agents" note flags this split as the original design intent)."""

from typing import Literal

from langchain_core.messages import HumanMessage
from pydantic import BaseModel

from app.services.llm import invoke_structured


Domain = Literal["sleep", "power", "posture", "iot", "general"]

DOMAINS: tuple[Domain, ...] = ("sleep", "power", "posture", "iot", "general")

_PROMPT_TEMPLATE = """사용자의 마지막 메시지가 어떤 도메인에 해당하는지 분류하세요. 정확히 하나만 고르세요.

- sleep: 수면 세션/점수/리포트, 수면 패턴에 대한 질문
- power: 기기 전력·에너지 사용량, 전력 리포트에 대한 질문
- posture: 자세, 제스처 로그에 대한 질문
- iot: 기기 목록 조회, 기기 제어, 반복 루틴/일정 조회 및 변경
- general: 위에 명확히 속하지 않거나 여러 도메인이 섞인 질문

사용자 메시지: {message}

domain 필드 하나만 담은 JSON으로 답하세요."""


class _Intent(BaseModel):
    domain: Domain = "general"


def _last_user_text(messages: list) -> str:
    for message in reversed(messages):
        if isinstance(message, HumanMessage):
            return str(message.content)
    return ""


async def classify_domain(messages: list) -> Domain:
    text = _last_user_text(messages)
    if not text:
        return "general"
    intent = await invoke_structured(
        _Intent, _PROMPT_TEMPLATE.format(message=text), fallback=_Intent(domain="general")
    )
    return intent.domain
