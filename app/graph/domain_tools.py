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
    make_automate_device_action_tool,
    make_cancel_schedule_tool,
    make_control_device_tool,
    make_create_alarm_tool,
    make_create_schedule_task_tool,
    make_delete_alarm_tool,
    make_delete_schedule_task_tool,
    make_execute_rule_tool,
    make_get_alarms_tool,
    make_get_camera_stream_tool,
    make_get_device_capabilities_tool,
    make_get_device_classes_tool,
    make_get_device_state_tool,
    make_get_ir_command_tool,
    make_get_ptz_capabilities_tool,
    make_get_schedule_tasks_tool,
    make_list_devices_tool,
    make_list_events_tool,
    make_list_ir_commands_tool,
    make_list_schedules_tool,
    make_ptz_move_tool,
    make_ptz_stop_tool,
    make_ptz_zoom_tool,
    make_query_db_tool,
    make_query_device_tool,
    make_rag_search_tool,
    make_schedule_device_action_tool,
    make_send_camera_tts_tool,
    make_set_camera_stream_tool,
    make_set_rule_enabled_tool,
    make_update_alarm_tool,
    make_update_schedule_task_tool,
)


DOMAIN_TABLES: dict[str, set[str]] = {
    "sleep": {"sleep_session", "sleep_stat", "sleep_report"},
    "power": {"power_energy", "power_report"},
    "posture": {"gesture_set", "gesture_log"},
    "iot": {"schedule_task", "device", "automation_rule", "alarm", "room", "room_user_map"},
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
        tools.append(make_get_device_capabilities_tool(user_id))
        tools.append(make_control_device_tool(user_id))
        tools.append(make_query_device_tool(user_id))
        tools.append(make_get_device_state_tool(user_id))
        tools.append(make_get_ptz_capabilities_tool(user_id))
        tools.append(make_ptz_move_tool(user_id))
        tools.append(make_ptz_stop_tool(user_id))
        tools.append(make_ptz_zoom_tool(user_id))
        tools.append(make_get_camera_stream_tool(user_id))
        tools.append(make_set_camera_stream_tool(user_id))
        tools.append(make_send_camera_tts_tool(user_id))
        tools.append(make_schedule_device_action_tool(user_id))
        tools.append(make_automate_device_action_tool(user_id))
        tools.append(make_list_schedules_tool(user_id))
        tools.append(make_cancel_schedule_tool(user_id))
        tools.append(make_get_schedule_tasks_tool(user_id))
        tools.append(make_create_schedule_task_tool(user_id))
        tools.append(make_update_schedule_task_tool(user_id))
        tools.append(make_delete_schedule_task_tool(user_id))
        tools.append(make_get_alarms_tool(user_id))
        tools.append(make_create_alarm_tool(user_id))
        tools.append(make_update_alarm_tool(user_id))
        tools.append(make_delete_alarm_tool(user_id))
        tools.append(make_get_device_classes_tool(user_id))
        tools.append(make_list_ir_commands_tool(user_id))
        tools.append(make_get_ir_command_tool(user_id))
        tools.append(make_list_events_tool(user_id))
        tools.append(make_execute_rule_tool(user_id))
        tools.append(make_set_rule_enabled_tool(user_id))
    elif domain == "power":
        # 실시간 순간 전력은 DB(power_energy)가 아니라 장치 query(power)로 읽는다.
        tools.append(make_list_devices_tool(user_id))
        tools.append(make_get_device_classes_tool(user_id))
        tools.append(make_get_device_capabilities_tool(user_id))
        tools.append(make_query_device_tool(user_id))
    return tools
