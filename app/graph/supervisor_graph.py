from typing import Any, Optional

from langgraph.graph import END, StateGraph

from app.graph import action_graph, chat_graph, report_graph
from app.state.agent_state import AgentState, AgentTask


_DEVICE_KEYWORDS = ["불", "조명", "에어컨", "온도", "소등"]
_SCHEDULE_KEYWORDS = ["일정", "운동", "내일", "옮겨"]
_REPORT_TASKS = {"weekly_sleep_report", "nightly_sleep_report", "weekly_posture_report", "daily_posture_report"}


async def load_user_context(state: AgentState) -> dict[str, Any]:
    # No user-profile API exists yet; extension point for e.g. display
    # name/timezone lookups once the C++ server exposes one.
    return {}


async def intent_classification(state: AgentState) -> dict[str, Any]:
    task = state["task"]
    if task != "chat":
        return {"intent": task}

    message = state.get("request", {}).get("message") or ""
    if any(k in message for k in _DEVICE_KEYWORDS):
        return {"intent": "device_control"}
    if any(k in message for k in _SCHEDULE_KEYWORDS):
        return {"intent": "schedule_management"}
    return {"intent": "health_chat"}


def route_graph(state: AgentState) -> str:
    task = state["task"]
    if task in _REPORT_TASKS:
        return "report_graph"
    if task == "recommend_actions":
        return "action_graph"
    if state["intent"] in ("device_control", "schedule_management"):
        return "action_graph"
    return "chat_graph"


def build():
    graph = StateGraph(AgentState)
    graph.add_node("load_user_context", load_user_context)
    graph.add_node("intent_classification", intent_classification)
    graph.add_node("chat_graph", chat_graph.build())
    graph.add_node("report_graph", report_graph.build())
    graph.add_node("action_graph", action_graph.build())

    graph.set_entry_point("load_user_context")
    graph.add_edge("load_user_context", "intent_classification")
    # Explicit path_map (not just the bare function) so draw_mermaid() can
    # resolve the branches instead of leaving chat_graph/report_graph/
    # action_graph as disconnected nodes in docs/graphs/supervisor_graph.png.
    graph.add_conditional_edges(
        "intent_classification",
        route_graph,
        {"chat_graph": "chat_graph", "report_graph": "report_graph", "action_graph": "action_graph"},
    )
    for node in ("chat_graph", "report_graph", "action_graph"):
        graph.add_edge(node, END)
    return graph.compile()


_supervisor = build()


async def run_agent(
    *,
    task: AgentTask,
    account_id: str,
    user_message: Optional[str] = None,
    metadata: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    initial_state: AgentState = {
        "task": task,
        "user_id": account_id,
        "request": {"message": user_message, "metadata": metadata or {}},
    }
    result = await _supervisor.ainvoke(initial_state)
    output = {"task": task, **result}
    if task == "chat" and "response" in output:
        output["answer"] = output["response"]
    return output
