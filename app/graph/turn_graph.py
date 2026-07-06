from typing import Any

from langchain_core.tools import BaseTool
from langgraph.graph.state import CompiledStateGraph

from app.graph.tool_loop import build_tool_loop
from app.state.chat_state import ChatTurnState


MAX_CHAT_ROUNDS = 6

_BANNED_PHRASES = ("진단합니다", "처방", "질병명")

_SYSTEM_PROMPT_TEMPLATE = """당신은 WaveHome의 건강 및 생활 어시스턴트입니다.

현재 시각: {now}

다음 tool을 사용해 사용자의 수면/자세/일정/기기 데이터를 조회하거나, 기기를 제어하거나, 일정을 변경할 수 있습니다:
query_db, rag_search, list_devices, control_device, get_routine_tasks, update_routine_task

query_db와 rag_search 사용 구분:
- "어젯밤", "오늘", "정확히 몇 점/몇 분" 처럼 정확한 최신 값이 필요하면 query_db를 먼저 쓰세요.
- "요즘", "최근", "패턴", "이전보다", "왜 그런지" 처럼 장기 맥락·비교·원인 설명이 필요하면 rag_search를
  먼저 써서 과거 리포트/패턴 요약을 찾고, 구체적 수치 확인이 필요하면 query_db로 보완하세요.
- 일정 변경(get_routine_tasks/update_routine_task)이나 기기 제어(list_devices/control_device)처럼
  정확한 현재 상태와 실행이 중요한 요청에는 rag_search를 쓰지 마세요.

규칙:
- 반드시 tool 호출로 얻은 사실에 근거해 답변하세요. 조회하지 않은 데이터를 추측해서 말하지 마세요.
- 의학적 진단이나 처방을 내리지 마세요. 필요하면 전문의 상담을 권유하세요.
- 기기 제어나 일정 변경 전에는 무엇을 할 것인지 명확히 파악한 뒤 실행하세요.
- 간결하고 친근한 한국어로 답변하세요.
"""

_RETRIEVED_SECTION_TEMPLATE = """

사전 검색된 참고자료 (필요하면 활용하고, 부족하면 tool로 추가 조회하세요):
{snippets}
"""


def _build_system_prompt(state: dict[str, Any]) -> str:
    prompt = _SYSTEM_PROMPT_TEMPLATE.format(now=state.get("now") or "알 수 없음")
    retrieved = state.get("retrieved") or []
    if retrieved:
        snippets = "\n".join(f"- [{r.get('collection')}] {r.get('text')}" for r in retrieved)
        prompt += _RETRIEVED_SECTION_TEMPLATE.format(snippets=snippets)
    return prompt


def build_chat_graph(tools: list[BaseTool]) -> CompiledStateGraph:
    return build_tool_loop(
        ChatTurnState,
        tools,
        max_rounds=MAX_CHAT_ROUNDS,
        system_prompt_fn=_build_system_prompt,
    )


def scrub_disclaimer(text: str) -> str:
    """Defense-in-depth: the system prompt already forbids this, but scrub any
    banned phrase that slips through, mirroring the old chat_graph.py's
    validate_response idea."""
    scrubbed = text
    for phrase in _BANNED_PHRASES:
        if phrase in scrubbed:
            scrubbed = scrubbed.replace(phrase, "").strip()
            scrubbed += " (이 답변은 의료적 진단이 아닙니다.)"
            break
    return scrubbed
