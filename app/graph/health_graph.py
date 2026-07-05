from typing import Any

from langgraph.graph import END, StateGraph

from app.agents import lifestyle_agent, observation_agent, posture_agent, sleep_agent
from app.models.insight import Insight
from app.services.insight_synthesis import synthesize
from app.state.agent_state import AgentState


_DOMAIN_NODES = {
    "sleep": "sleep_agent",
    "posture": "posture_agent",
    "observation": "observation_agent",
    "lifestyle": "lifestyle_agent",
}
_INSIGHT_KEYS = ("sleep_insight", "posture_insight", "observation_insight", "lifestyle_insight")


async def task_planning(state: AgentState) -> dict[str, Any]:
    # required_context is set by the caller (chat_graph/action_graph); this
    # node exists as a named extension point (design.md's HealthAnalysisGraph).
    return {}


def select_domain_agents(state: AgentState) -> list[str]:
    required = state.get("required_context") or list(_DOMAIN_NODES)
    return [_DOMAIN_NODES[domain] for domain in required if domain in _DOMAIN_NODES]


async def insight_synthesizer(state: AgentState) -> dict[str, Any]:
    insights = [Insight.model_validate(state[key]) for key in _INSIGHT_KEYS if state.get(key)]
    return {"health_insights": synthesize(insights).model_dump()}


def build():
    graph = StateGraph(AgentState)
    graph.add_node("task_planning", task_planning)
    graph.add_node("sleep_agent", sleep_agent.run)
    graph.add_node("posture_agent", posture_agent.run)
    graph.add_node("observation_agent", observation_agent.run)
    graph.add_node("lifestyle_agent", lifestyle_agent.run)
    graph.add_node("insight_synthesizer", insight_synthesizer)

    graph.set_entry_point("task_planning")
    # path returns a *list* of node names -> true parallel fan-out; `then`
    # names the join node that runs once all selected agents finish.
    graph.add_conditional_edges("task_planning", select_domain_agents, then="insight_synthesizer")
    graph.add_edge("insight_synthesizer", END)
    return graph.compile()
