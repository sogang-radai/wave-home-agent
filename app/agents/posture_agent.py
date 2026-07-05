import json
from datetime import date, timedelta
from typing import Any

from app.clients.core import ToolError
from app.models.insight import Insight
from app.services.llm import invoke_structured
from app.services.prompts import load_prompt
from app.state.agent_state import AgentState
from app.tools.posture_api import get_posture_summary


def _rule_based_insight(data: dict[str, Any]) -> Insight:
    score = data.get("score", 0)
    risk_level = "low" if score >= 80 else "medium" if score >= 60 else "high"
    turtle_neck_count = data.get("turtle_neck_count", 0)
    max_sitting = data.get("max_continuous_sitting_minutes", 0)

    return Insight(
        domain="posture",
        summary=(
            f"최근 자세 점수는 {score}점이며, 정자세 비율은 "
            f"{data.get('correct_posture_percent', 'N/A')}%입니다."
        ),
        risk_level=risk_level,
        positive_points=["정자세 유지 비율이 양호합니다."] if risk_level == "low" else [],
        negative_points=(
            [f"거북목이 {turtle_neck_count}회 감지되었고, 최대 연속 착석 시간이 {max_sitting}분입니다."]
            if risk_level != "low"
            else []
        ),
        recommendations=["1시간마다 자리에서 일어나 스트레칭을 해보세요."],
        confidence=0.5,
    )


async def run(state: AgentState) -> dict[str, Any]:
    today = date.today()
    week_ago = today - timedelta(days=7)
    try:
        data = await get_posture_summary(state["user_id"], week_ago.isoformat(), today.isoformat())
    except ToolError:
        fallback = Insight(
            domain="posture",
            summary="자세 데이터를 가져오지 못했습니다.",
            risk_level="unknown",
            confidence=0.0,
        )
        return {"posture_insight": fallback.model_dump(), "errors": ["posture tool call failed"]}

    fallback = _rule_based_insight(data)
    prompt = load_prompt(
        "posture",
        "insight",
        data=json.dumps(data, ensure_ascii=False),
        question=state.get("request", {}).get("message") or "",
    )
    insight = await invoke_structured(Insight, prompt, fallback=fallback)
    return {"posture_insight": insight.model_dump()}
