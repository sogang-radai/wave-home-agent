import json
from typing import Any

from pydantic import BaseModel, Field

from app.services.llm import invoke_structured
from app.services.prompts import load_prompt
from app.state.agent_state import AgentState
from app.tools.report_api import get_report_context


_TITLES = {
    "weekly_sleep_report": "이번 주 수면 리포트",
    "nightly_sleep_report": "어젯밤 수면 리포트",
    "weekly_posture_report": "이번 주 자세 리포트",
    "daily_posture_report": "오늘의 자세 리포트",
}


class ReportContent(BaseModel):
    summary: str
    highlights: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)


async def report_type(state: AgentState) -> dict[str, Any]:
    task = state["task"]
    return {"report": {"title": _TITLES[task], "summary": "", "highlights": [], "recommendations": [], "sources": []}}


async def collect_data(state: AgentState) -> dict[str, Any]:
    context = await get_report_context(state["user_id"], state["task"])
    return {"tool_results": context, "report": {**state["report"], "sources": ["core-api"]}}


async def sleep_summary(state: AgentState) -> dict[str, Any]:
    sleep = state.get("tool_results", {}).get("sleep")
    if not sleep:
        return {}
    highlight = f"수면 점수 {sleep['score']}점, 평균 수면 {sleep.get('avg_sleep_minutes', 'N/A')}분"
    return {"report": {**state["report"], "highlights": [*state["report"]["highlights"], highlight]}}


async def posture_summary(state: AgentState) -> dict[str, Any]:
    posture = state.get("tool_results", {}).get("posture")
    if not posture:
        return {}
    highlight = f"자세 점수 {posture['score']}점, 정자세 비율 {posture.get('correct_posture_percent', 'N/A')}%"
    return {"report": {**state["report"], "highlights": [*state["report"]["highlights"], highlight]}}


async def observation_summary(state: AgentState) -> dict[str, Any]:
    # No observation data source is wired into report_api yet (mock-only tool,
    # see app/tools/observation_api.py); reserved as a pass-through extension point.
    return {}


async def trend_analysis(state: AgentState) -> dict[str, Any]:
    for domain_data in state.get("tool_results", {}).values():
        trend = domain_data.get("trend")
        if trend == "slightly_worse":
            highlight = "최근 추세가 지난주 대비 다소 저하되었습니다."
            return {"report": {**state["report"], "highlights": [*state["report"]["highlights"], highlight]}}
    return {}


def _rule_based_content(state: AgentState) -> ReportContent:
    highlights = state["report"]["highlights"]
    summary = "; ".join(highlights) if highlights else "특이사항이 없는 안정적인 한 주였습니다."
    return ReportContent(
        summary=summary,
        highlights=highlights,
        recommendations=["취침 전 조명과 실내 온도를 일정하게 유지하세요.", "장시간 앉아 있는 구간에는 짧은 스트레칭을 추가하세요."],
    )


async def recommendation(state: AgentState) -> dict[str, Any]:
    fallback = _rule_based_content(state)
    prompt = load_prompt(
        "report",
        "recommendation",
        report_title=state["report"]["title"],
        data=json.dumps(state.get("tool_results", {}), ensure_ascii=False),
    )
    content = await invoke_structured(ReportContent, prompt, fallback=fallback)
    return {
        "report": {
            **state["report"],
            "summary": content.summary,
            "highlights": content.highlights or state["report"]["highlights"],
            "recommendations": content.recommendations,
        }
    }


async def generate_json(state: AgentState) -> dict[str, Any]:
    # Flatten the internal "report" draft into the top-level AgentState keys
    # that app/schemas/agent.py::ReportResponse expects.
    report = state["report"]
    return {
        "title": report["title"],
        "summary": report["summary"],
        "highlights": report["highlights"],
        "recommendations": report["recommendations"],
        "sources": report["sources"],
    }
