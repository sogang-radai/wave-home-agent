import json
from datetime import date, timedelta
from typing import Any

from app.models.insight import Insight
from app.services.llm import invoke_structured
from app.services.prompts import load_prompt
from app.state.agent_state import AgentState
from app.tools.observation_api import get_observation_summary


def _rule_based_insight(data: dict[str, Any]) -> Insight:
    events = data.get("night_activity_events", 0)
    risk_level = "low" if events == 0 else "medium"

    return Insight(
        domain="observation",
        summary=f"최근 활동 수준은 '{data.get('activity_level', 'normal')}'로 관측되었습니다.",
        risk_level=risk_level,
        negative_points=data.get("notes", []),
        recommendations=["야간 활동이 잦다면 취침 전 루틴을 점검해보세요."] if events > 0 else [],
        confidence=0.3,
    )


async def run(state: AgentState) -> dict[str, Any]:
    today = date.today()
    week_ago = today - timedelta(days=7)
    data = await get_observation_summary(state["user_id"], week_ago.isoformat(), today.isoformat())

    fallback = _rule_based_insight(data)
    prompt = load_prompt(
        "observation",
        "insight",
        data=json.dumps(data, ensure_ascii=False),
        question=state.get("request", {}).get("message") or "",
    )
    insight = await invoke_structured(Insight, prompt, fallback=fallback)
    return {"observation_insight": insight.model_dump()}
