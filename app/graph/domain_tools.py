"""Domain-scoped tool sets for the chat subgraphs (app/graph/chat_subgraphs.py).

query_db/rag_search are restricted to the tables/collections relevant to one
domain (make_query_db_tool/make_rag_search_tool enforce this in
app/graph/tools.py) so a domain subgraph can't be steered into reading another
domain's rows - the same defense-in-depth spirit as tools.py's userId pinning.
"""

from langchain_core.tools import BaseTool

from app.graph.domain_router import Domain
from app.graph.tools import (
    build_tools,
    make_control_device_tool,
    make_get_routine_tasks_tool,
    make_list_devices_tool,
    make_query_db_tool,
    make_rag_search_tool,
    make_update_routine_task_tool,
)


DOMAIN_TABLES: dict[str, set[str]] = {
    "sleep": {"sleep_session", "sleep_stat", "sleep_report"},
    "power": {"power_energy", "power_report"},
    "posture": {"gesture_set", "gesture_log"},
    "iot": {"schedule_task", "device"},
}

DOMAIN_RAG_COLLECTIONS: dict[str, set[str]] = {
    "sleep": {"sleep_report", "sleep_stat"},
    "power": {"power_report"},
}


def build_domain_tools(domain: Domain, user_id: int) -> list[BaseTool]:
    if domain == "general":
        return build_tools(user_id)

    tools: list[BaseTool] = []
    tables = DOMAIN_TABLES.get(domain)
    if tables:
        tools.append(make_query_db_tool(user_id, allowed_tables=tables))
    collections = DOMAIN_RAG_COLLECTIONS.get(domain)
    if collections:
        tools.append(make_rag_search_tool(allowed_collections=collections))
    if domain == "iot":
        tools.append(make_list_devices_tool(user_id))
        tools.append(make_control_device_tool(user_id))
        tools.append(make_get_routine_tasks_tool(user_id))
        tools.append(make_update_routine_task_tool(user_id))
    return tools
