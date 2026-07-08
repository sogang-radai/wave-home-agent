"""Classifies a chat turn into one or more tool domains so turn_graph.py can
fan out to each domain's subgraph in parallel and synthesize a single answer,
instead of dispatching the whole turn to exactly one domain."""

from typing import Literal, Optional

from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig
from pydantic import BaseModel, Field

from app.services.llm import invoke_structured


Domain = Literal["sleep", "power", "posture", "iot", "general"]

DOMAINS: tuple[Domain, ...] = ("sleep", "power", "posture", "iot", "general")

_PROMPT_TEMPLATE = """사용자의 마지막 메시지에 해당하는 도메인을 모두 골라 배열로 답하세요.

- sleep: 수면 세션/점수/리포트, 수면 패턴에 대한 질문
- power: 기기 전력·에너지 사용량, 전력 리포트에 대한 질문
- posture: 자세, 제스처 로그에 대한 질문
- iot: 기기 목록 조회, 기기 제어, 반복 루틴/일정 조회 및 변경
- general: 위 도메인에 명확히 속하지 않는 일반적인 질문이나 인사말일 때만 포함하세요

여러 도메인이 관련된 질문(예: "이번 주 전반적인 건강 알려줘")이면 해당하는 도메인을 모두 배열에 포함하세요.
관련 도메인이 하나도 명확하지 않으면 ["general"]만 반환하세요.

사용자 메시지: {message}

domains 필드(문자열 배열, 1개 이상)만 담은 JSON으로 답하세요."""


class _Intent(BaseModel):
    domains: list[Domain] = Field(default_factory=lambda: ["general"])


def _last_user_text(messages: list) -> str:
    for message in reversed(messages):
        if isinstance(message, HumanMessage):
            return str(message.content)
    return ""


async def classify_domains(messages: list, *, config: Optional[RunnableConfig] = None) -> list[Domain]:
    text = _last_user_text(messages)
    if not text:
        return ["general"]
    intent = await invoke_structured(
        _Intent,
        _PROMPT_TEMPLATE.format(message=text),
        fallback=_Intent(domains=["general"]),
        config=config,
    )
    domains = list(dict.fromkeys(intent.domains))
    # The prompt asks the model to only include "general" when nothing else
    # clearly applies, but it isn't a hard constraint - if it slips in
    # alongside a specific domain anyway, drop it rather than let a
    # full-access fallback agent duplicate/contradict the specific one.
    if len(domains) > 1 and "general" in domains:
        domains = [d for d in domains if d != "general"]
    return domains or ["general"]
