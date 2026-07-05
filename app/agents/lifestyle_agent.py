import json
from typing import Any

from app.clients.core import ToolError
from app.models.insight import Insight
from app.services.llm import invoke_structured
from app.services.prompts import load_prompt
from app.state.agent_state import AgentState
from app.tools.observation_api import get_observation_summary
from app.tools.schedule_api import get_schedule


def _rule_based_insight(data: dict[str, Any]) -> Insight:
    schedule = data.get("schedule", [])
    pending = [task for task in schedule if not task.get("done")]
    risk_level = "low" if not pending else "medium"

    return Insight(
        domain="lifestyle",
        summary=f"이번 주 예정된 일정 {len(schedule)}건 중 {len(pending)}건이 아직 진행 전입니다.",
        risk_level=risk_level,
        positive_points=["일정을 꾸준히 이행하고 있습니다."] if not pending else [],
        negative_points=[f"'{task['title']}' 일정이 아직 완료되지 않았습니다." for task in pending],
        recommendations=["운동이나 생활 습관 일정을 놓치지 않도록 알림을 확인해보세요."] if pending else [],
        confidence=0.4,
    )


async def run(state: AgentState) -> dict[str, Any]:
    try:
        schedule = await get_schedule(state["user_id"])
    except ToolError:
        fallback = Insight(
            domain="lifestyle",
            summary="일정 데이터를 가져오지 못했습니다.",
            risk_level="unknown",
            confidence=0.0,
        )
        return {"lifestyle_insight": fallback.model_dump(), "errors": ["schedule tool call failed"]}

    observation = await get_observation_summary(state["user_id"])
    data = {"schedule": schedule, "observation": observation}

    fallback = _rule_based_insight(data)
    prompt = load_prompt(
        "lifestyle",
        "insight",
        data=json.dumps(data, ensure_ascii=False),
        question=state.get("request", {}).get("message") or "",
    )
    insight = await invoke_structured(Insight, prompt, fallback=fallback)
    return {"lifestyle_insight": insight.model_dump()}
