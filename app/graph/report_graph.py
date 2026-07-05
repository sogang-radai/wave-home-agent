from langgraph.graph import END, StateGraph

from app.agents import report_agent
from app.state.agent_state import AgentState


def build():
    graph = StateGraph(AgentState)
    graph.add_node("report_type", report_agent.report_type)
    graph.add_node("collect_data", report_agent.collect_data)
    graph.add_node("sleep_summary", report_agent.sleep_summary)
    graph.add_node("posture_summary", report_agent.posture_summary)
    graph.add_node("observation_summary", report_agent.observation_summary)
    graph.add_node("trend_analysis", report_agent.trend_analysis)
    graph.add_node("recommendation", report_agent.recommendation)
    graph.add_node("generate_json", report_agent.generate_json)

    graph.set_entry_point("report_type")
    graph.add_edge("report_type", "collect_data")
    graph.add_edge("collect_data", "sleep_summary")
    graph.add_edge("sleep_summary", "posture_summary")
    graph.add_edge("posture_summary", "observation_summary")
    graph.add_edge("observation_summary", "trend_analysis")
    graph.add_edge("trend_analysis", "recommendation")
    graph.add_edge("recommendation", "generate_json")
    graph.add_edge("generate_json", END)
    return graph.compile()
