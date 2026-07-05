import json
from datetime import date, timedelta
from typing import Any

from app.clients.core import ToolError
from app.models.insight import Insight
from app.services.llm import invoke_structured
from app.services.prompts import load_prompt
from app.state.agent_state import AgentState
from app.tools.sleep_api import get_sleep_summary


def _rule_based_insight(data: dict[str, Any]) -> Insight:
    score = data.get("score", 0)
    risk_level = "low" if score >= 80 else "medium" if score >= 60 else "high"
    wake_ups = data.get("wake_ups", 0)

    return Insight(
        domain="sleep",
        summary=(
            f"최근 수면 점수는 {score}점이며, 하루 평균 {data.get('avg_sleep_minutes', 'N/A')}분 "
            f"주무셨습니다. 중간 각성은 {wake_ups}회로 기록되어 있습니다."
        ),
        risk_level=risk_level,
        positive_points=["침대에 머무는 시간이 안정적으로 유지되고 있습니다."] if risk_level == "low" else [],
        negative_points=[f"최근 중간 각성이 {wake_ups}회 있었습니다."] if wake_ups > 0 else [],
        recommendations=["취침 30분 전 조명을 낮추고 카페인 섭취를 줄여보세요."],
        confidence=0.5,
    )


async def run(state: AgentState) -> dict[str, Any]:
    today = date.today()
    week_ago = today - timedelta(days=7)
    try:
        data = await get_sleep_summary(state["user_id"], week_ago.isoformat(), today.isoformat())
    except ToolError:
        fallback = Insight(
            domain="sleep",
            summary="수면 데이터를 가져오지 못했습니다.",
            risk_level="unknown",
            confidence=0.0,
        )
        return {"sleep_insight": fallback.model_dump(), "errors": ["sleep tool call failed"]}

    fallback = _rule_based_insight(data)
    prompt = load_prompt(
        "sleep",
        "insight",
        data=json.dumps(data, ensure_ascii=False),
        question=state.get("request", {}).get("message") or "",
    )
    insight = await invoke_structured(Insight, prompt, fallback=fallback)
    return {"sleep_insight": insight.model_dump()}
