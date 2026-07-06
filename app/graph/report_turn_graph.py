import json
from typing import Any

from langchain_core.messages import HumanMessage, ToolMessage
from langgraph.graph import END, StateGraph
from pydantic import BaseModel, Field

from app.graph.tool_loop import build_tool_loop
from app.graph.tools import make_query_db_tool, make_rag_search_tool
from app.services.llm import invoke_structured
from app.services.prompts import load_prompt
from app.state.report_turn_state import ReportTurnState


MAX_CONTEXT_ROUNDS = 2

_TITLES = {
    ("sleep", "daily"): "어젯밤 수면 리포트",
    ("sleep", "weekly"): "이번 주 수면 리포트",
    ("posture", "daily"): "오늘의 자세 리포트",
    ("posture", "weekly"): "이번 주 자세 리포트",
}

_CONTEXT_SYSTEM_PROMPT = """당신은 WaveHome 리포트 작성을 돕는 조사자입니다.
주어진 지표(metrics)와 원본 데이터(raw)만으로 패턴을 설명하기 부족할 때만 추가로 조회하세요.

- 지난 기간과의 비교, 반복되는 패턴 등 서술적 맥락이 필요하면 rag_search로 과거 리포트를 먼저 찾으세요.
- 정확한 수치 확인이 필요하면 query_db를 쓰세요.

필요 없으면 tool을 호출하지 말고 "충분합니다"라고만 답하세요."""


class ReportContent(BaseModel):
    summary: str
    highlights: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)


def _title(state: dict[str, Any]) -> str:
    return _TITLES.get((state["domain"], state["period"]), f"{state['domain']} {state['period']} 리포트")


def _seed_message(state: dict[str, Any]) -> HumanMessage:
    return HumanMessage(
        content=(
            f"리포트 종류: {_title(state)}\n"
            f"기간 시작: {state['period_start']}\n"
            f"지표(metrics): {json.dumps(state['metrics'], ensure_ascii=False)}\n"
            f"원본 데이터(raw): {json.dumps(state.get('raw') or {}, ensure_ascii=False)}"
        )
    )


def _extract_tool_results(messages: list[Any]) -> list[Any]:
    extra = []
    for message in messages:
        if isinstance(message, ToolMessage):
            try:
                extra.append(json.loads(str(message.content)))
            except (TypeError, ValueError):
                extra.append(str(message.content))
    return extra


def _rule_based_content(state: dict[str, Any]) -> ReportContent:
    metrics = state["metrics"]
    summary = "; ".join(f"{k}: {v}" for k, v in metrics.items()) or "제공된 지표가 없습니다."
    return ReportContent(
        summary=summary,
        highlights=[],
        recommendations=["취침/기상 시간을 일정하게 유지하세요.", "장시간 같은 자세를 피하고 틈틈이 스트레칭하세요."],
    )


async def gather_extra_context(state: ReportTurnState) -> dict[str, Any]:
    tools = [make_query_db_tool(state["user_id"]), make_rag_search_tool()]
    loop = build_tool_loop(
        ReportTurnState,
        tools,
        max_rounds=MAX_CONTEXT_ROUNDS,
        system_prompt_fn=lambda _state: _CONTEXT_SYSTEM_PROMPT,
    )
    result = await loop.ainvoke({"messages": [_seed_message(state)], "rounds": 0})
    return {"messages": result["messages"]}


async def generate_content(state: ReportTurnState) -> dict[str, Any]:
    extra_context = _extract_tool_results(state.get("messages", []))
    data = {"metrics": state["metrics"], "raw": state.get("raw"), "extraContext": extra_context}
    fallback = _rule_based_content(state)
    prompt = load_prompt("report", "recommendation", report_title=_title(state), data=json.dumps(data, ensure_ascii=False))
    content = await invoke_structured(ReportContent, prompt, fallback=fallback)
    return {"content": content.model_dump()}


def build():
    graph = StateGraph(ReportTurnState)
    graph.add_node("gather_extra_context", gather_extra_context)
    graph.add_node("generate_content", generate_content)
    graph.set_entry_point("gather_extra_context")
    graph.add_edge("gather_extra_context", "generate_content")
    graph.add_edge("generate_content", END)
    return graph.compile()
