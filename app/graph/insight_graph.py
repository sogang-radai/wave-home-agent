"""insight-generation-api.md 의 `/insight/v1/insights` 생성 그래프.

app/graph/report_turn_graph.py 와 동일한 2-노드 gather->generate 패턴을 재사용한다:
에이전트가 db/query·rag/search 툴로 부족한 데이터를 스스로 조회(gather)한 뒤,
그 결과를 근거로 구조화 출력을 생성(generate)한다. sleep/power 리포트와 달리
백엔드가 metrics 를 인라인으로 주지 않으므로 이 패턴이 적합하다.

SURFACE_TABLES/SURFACE_RAG_COLLECTIONS 매핑은 insight-generation-api.md 에 명시되지
않은 추정치다(db-schema.md 의 insight.surface 값과 rag-api.md 의 insight_* 컬렉션
대응 관계를 근거로 구성). 실제 사용 시 팀원 확인 필요.
"""

import json
from typing import Any

from langchain_core.messages import HumanMessage, ToolMessage
from langgraph.graph import END, StateGraph

from app.graph.tool_loop import build_tool_loop
from app.graph.tools import make_query_db_tool, make_rag_search_tool
from app.schemas.insight import GeneratedInsightBatch
from app.services.llm import invoke_structured
from app.services.prompts import load_prompt
from app.state.insight_state import InsightGenerationState


MAX_CONTEXT_ROUNDS = 2

SURFACE_TABLES: dict[str, set[str]] = {
    "dashboard_banner": {"sleep_report", "power_report", "schedule_task", "alarm"},
    "weekly_plan": {"schedule_task", "sleep_report", "posture_report", "weekly_plan_report"},
    "sleep_report": {"sleep_session", "sleep_stat", "sleep_report"},
    "posture_report": {"gesture_log", "posture_stat", "posture_report"},
    "power": {"power_energy", "power_report"},
}

SURFACE_RAG_COLLECTIONS: dict[str, set[str]] = {
    "dashboard_banner": {"insight_dashboard"},
    "weekly_plan": {"weekly_plan_report", "insight_weekly_plan"},
    "sleep_report": {"sleep_report", "sleep_stat", "insight_sleep"},
    "posture_report": {"posture_report", "insight_posture"},
    "power": {"power_report", "insight_power"},
}

_CONTEXT_SYSTEM_PROMPT = """당신은 WaveHome 인사이트 생성을 돕는 조사자입니다.
주어진 힌트(context)만으로 인사이트를 만들기 부족할 때만 db/query·rag_search 로 추가 조회하세요.
필요 없으면 tool을 호출하지 말고 "충분합니다"라고만 답하세요."""


def _seed_message(state: InsightGenerationState) -> HumanMessage:
    return HumanMessage(
        content=(
            f"surface: {state['surface']}\n"
            f"date: {state['date']}\n"
            f"context: {json.dumps(state.get('context') or {}, ensure_ascii=False)}"
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


async def gather(state: InsightGenerationState) -> dict[str, Any]:
    surface = state["surface"]
    tools = [
        make_query_db_tool(state["user_id"], allowed_tables=SURFACE_TABLES.get(surface, set())),
        make_rag_search_tool(allowed_collections=SURFACE_RAG_COLLECTIONS.get(surface, set())),
    ]
    loop = build_tool_loop(
        InsightGenerationState,
        tools,
        max_rounds=MAX_CONTEXT_ROUNDS,
        system_prompt_fn=lambda _state: _CONTEXT_SYSTEM_PROMPT,
    )
    result = await loop.ainvoke({"messages": [_seed_message(state)], "rounds": 0})
    return {"messages": result["messages"]}


async def generate(state: InsightGenerationState) -> dict[str, Any]:
    extra_context = _extract_tool_results(state.get("messages", []))
    prompt = load_prompt(
        "insight",
        "generate",
        user_id=state["user_id"],
        surface=state["surface"],
        date=state["date"],
        context=json.dumps(state.get("context") or {}, ensure_ascii=False),
        extra_context=json.dumps(extra_context, ensure_ascii=False),
    )
    batch = await invoke_structured(GeneratedInsightBatch, prompt, fallback=GeneratedInsightBatch(items=[]))
    return {"items": [item.model_dump() for item in batch.items]}


def build():
    graph = StateGraph(InsightGenerationState)
    graph.add_node("gather", gather)
    graph.add_node("generate", generate)
    graph.set_entry_point("gather")
    graph.add_edge("gather", "generate")
    graph.add_edge("generate", END)
    return graph.compile()
