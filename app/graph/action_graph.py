from typing import Any

from langgraph.graph import END, StateGraph

from app.agents import device_agent, schedule_agent
from app.graph import health_graph
from app.models.action import ActionPlan
from app.state.agent_state import AgentState


async def intent_analysis(state: AgentState) -> dict[str, Any]:
    # Supervisor already classified the intent before routing here.
    return {"intent": state.get("intent", state["task"])}


async def action_planning(state: AgentState) -> dict[str, Any]:
    intent = state["intent"]
    message = state.get("request", {}).get("message") or ""

    if intent == "device_control":
        is_ac = any(k in message for k in ("에어컨", "온도"))
        plan = ActionPlan(
            type="device_control",
            description="가전 제어 요청을 실행합니다.",
            target={
                "device_id": "ac_bedroom" if is_ac else "light_living_room",
                "control_id": "temperature" if is_ac else "power",
                "value": None,
            },
        )
    elif intent == "schedule_management":
        plan = ActionPlan(
            type="schedule_update",
            description="일정 변경 요청을 실행합니다.",
            target={"task_id": "task_exercise_tonight", "changes": {"day_of_week": "tue"}},
        )
    else:  # recommend_actions
        plan = ActionPlan(type="schedule_update", description="추천 액션을 생성합니다.", target={})
    return {"action_plan": plan.model_dump()}


def route_by_intent(state: AgentState) -> str:
    intent = state["intent"]
    if intent == "device_control":
        return "device_agent"
    if intent == "schedule_management":
        return "schedule_agent"
    return "set_recommend_context"


async def set_recommend_context(state: AgentState) -> dict[str, Any]:
    return {"required_context": ["sleep", "posture", "lifestyle"]}


async def recommend_finalize(state: AgentState) -> dict[str, Any]:
    health = state.get("health_insights", {})
    actions = [{"type": "automation_suggestion", "description": rec} for rec in health.get("recommendations", [])]
    return {"action_plan": {**state["action_plan"], "target": {"actions": actions}}}


async def verify_result(state: AgentState) -> dict[str, Any]:
    # device_agent/schedule_agent already re-read backend state to confirm
    # the write applied; this node is a named extension point for future
    # cross-checks (design.md's ActionGraph "Verify Result").
    return {}


async def generate_response(state: AgentState) -> dict[str, Any]:
    if state["intent"] == "recommend_actions":
        health = state.get("health_insights", {})
        actions = state["action_plan"].get("target", {}).get("actions", [])
        return {
            "summary": health.get("summary", "추천할 액션을 준비했습니다."),
            "recommendations": health.get("recommendations", []),
            "actions": actions,
            "sources": ["core-api"],
        }

    plan = state["action_plan"]
    result = state["action_result"]
    action_entry = {"type": plan["type"], "status": result["status"], "description": plan["description"]}
    if result["status"] == "ok":
        response = result["detail"]
    else:
        response = f"요청을 처리하지 못했습니다: {result['detail']}"
    return {"response": response, "actions": [action_entry], "sources": ["core-api"]}


def build():
    graph = StateGraph(AgentState)
    graph.add_node("intent_analysis", intent_analysis)
    graph.add_node("action_planning", action_planning)
    graph.add_node("device_agent", device_agent.run)
    graph.add_node("schedule_agent", schedule_agent.run)
    graph.add_node("set_recommend_context", set_recommend_context)
    graph.add_node("health_analysis", health_graph.build())
    graph.add_node("recommend_finalize", recommend_finalize)
    graph.add_node("verify_result", verify_result)
    graph.add_node("generate_response", generate_response)

    graph.set_entry_point("intent_analysis")
    graph.add_edge("intent_analysis", "action_planning")
    graph.add_conditional_edges("action_planning", route_by_intent)
    graph.add_edge("device_agent", "verify_result")
    graph.add_edge("schedule_agent", "verify_result")
    graph.add_edge("set_recommend_context", "health_analysis")
    graph.add_edge("health_analysis", "recommend_finalize")
    graph.add_edge("recommend_finalize", "verify_result")
    graph.add_edge("verify_result", "generate_response")
    graph.add_edge("generate_response", END)
    return graph.compile()
