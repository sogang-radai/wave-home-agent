"""LangChain @tool wrappers around app/tools/*.py mock functions.

Tools are built fresh per chat turn via build_tools(user_id), closing over the
authenticated userId from the request body. Device/schedule tools never let
the model supply userId (api.md frames it as authorization, not a filter).
query_db is the one exception: filter.userId is legitimate row-filter data the
model must supply, so make_query_db_tool injects/overwrites it server-side
instead of trusting whatever the model passes, to block a prompt-injected
cross-user data request.
"""

import json
from typing import Any, Literal, Optional

from langchain_core.tools import BaseTool, tool
from pydantic import BaseModel, Field

from app.tools.db_query import TABLE_SPECS, DbQuery, DbQueryError, DbQueryResultItem, MAX_QUERIES, query_db
from app.tools import devices_internal, rules_internal
from app.tools.devices_internal import ExecMode, InvokeDeviceRequest, QueryDeviceRequest
from app.tools.rag_search import RagTarget, rag_search
from app.tools.routine_tasks_internal import get_routine_tasks, update_routine_task
from app.tools.rules_internal import CreateRuleRequest, RuleAction, RuleSchedule


class _QueryDbArgs(BaseModel):
    queries: list[DbQuery] = Field(..., description="최대 10개의 배치 조회. api.md §2.1 참고.")


_QUERY_DB_USAGE = """정확한 최신 값이 필요할 때 사용하세요: 특정 날짜의 수면 세션/통계, 오늘 일정, 정확한 점수/시간 등
구조화된 raw row를 조회합니다. "어젯밤", "오늘", "정확히 몇 점" 같은 질문에 적합합니다."""


def _describe_table(table: str) -> str:
    """Renders one TABLE_SPECS entry (app/tools/db_query.py) as a line for the
    query_db tool description, so the model sees the real per-table filter
    rules up front instead of learning them from an INVALID_FILTER error on
    its first guess."""
    spec = TABLE_SPECS.get(table)
    if spec is None:
        return f"- {table}"
    optional = sorted(spec.allowed - spec.required_any)
    bits = []
    if spec.required_any:
        bits.append(f"{'|'.join(sorted(spec.required_any))} 중 최소 1개 필수")
    if optional:
        bits.append(f"선택 필터: {', '.join(optional)}")
    line = f"- {table}: " + (" / ".join(bits) if bits else "필터 없음")
    if "userId" in spec.allowed:
        line += " (userId는 값과 무관하게 현재 사용자로 고정되지만, 키 자체는 반드시 포함해야 함)"
    return line


def _describe_tables(tables: set[str]) -> str:
    return "\n".join(_describe_table(t) for t in sorted(tables) if t in TABLE_SPECS)


def make_query_db_tool(user_id: int, *, allowed_tables: Optional[set[str]] = None) -> BaseTool:
    """allowed_tables restricts which `table` values a domain subgraph may query
    (app/graph/domain_tools.py). Disallowed tables come back as a per-query
    INVALID_FILTER error, same shape as db_query.py's own table validation,
    instead of silently dropping or reaching the real backend.

    The tool description is generated from TABLE_SPECS (app/tools/db_query.py)
    - the actual validation rules - rather than hand-written prose, so it
    can't drift out of sync with them, and each domain only sees the rules
    for tables it's actually allowed to query."""
    tables = allowed_tables if allowed_tables is not None else set(TABLE_SPECS)
    description = f"{_QUERY_DB_USAGE}\n\n테이블별 filter 규칙:\n{_describe_tables(tables)}"

    async def _query_db(queries: list[DbQuery]) -> str:
        for q in queries:
            if "userId" in q.filter:
                q.filter["userId"] = user_id

        results: list[DbQueryResultItem] = []
        for q in queries[:MAX_QUERIES]:
            if allowed_tables is not None and q.table not in allowed_tables:
                results.append(
                    DbQueryResultItem(
                        table=q.table,
                        count=0,
                        items=[],
                        error=DbQueryError(
                            code="INVALID_FILTER",
                            message=f"이 도메인에서는 조회할 수 없는 테이블입니다: {q.table}",
                            field="table",
                        ),
                    )
                )
                continue
            results.extend(await query_db([q]))
        return _to_json([r.model_dump() for r in results])

    return tool("query_db", _query_db, description=description, args_schema=_QueryDbArgs)


class _RagSearchArgs(BaseModel):
    query: str = Field(..., description="검색할 자연어 질의")
    targets: list[RagTarget] = Field(..., description="검색 대상 컬렉션 목록. api.md §2.6 참고.")


def make_rag_search_tool(*, allowed_collections: Optional[set[str]] = None) -> BaseTool:
    """allowed_collections restricts which rag_search collections a domain
    subgraph may target (app/graph/domain_tools.py); other targets are dropped
    before the call."""

    @tool("rag_search", args_schema=_RagSearchArgs)
    async def _rag_search(query: str, targets: list[RagTarget]) -> str:
        """과거에 만들어진 자연어 요약(리포트 문장, 기간별 패턴 설명)을 의미 기반으로 검색합니다.
        "요즘", "최근", "패턴", "이전보다", "왜 그런지" 같은 장기 맥락·비교·원인 질문에 적합합니다.
        정확한 최신 수치가 필요하면 query_db를 대신 쓰세요."""
        if allowed_collections is not None:
            targets = [t for t in targets if t.collection in allowed_collections]
        if not targets:
            return _to_json([])
        results = await rag_search(query, targets)
        return _to_json([r.model_dump() for r in results])

    return _rag_search


class _ListDevicesArgs(BaseModel):
    room_id: Optional[int] = Field(None, description="조회할 방 ID (생략 시 전체)")


def make_list_devices_tool(user_id: int) -> BaseTool:
    @tool("list_devices", args_schema=_ListDevicesArgs)
    async def _list_devices(room_id: Optional[int] = None) -> str:
        """방에 속한 가전 기기 요약(연결 상태 포함)을 조회합니다. 세부 action/query 는
        get_device_capabilities 로 확인하세요."""
        devices = await devices_internal.list_devices(user_id=user_id, room_id=room_id)
        return _to_json([d.model_dump(by_alias=True) for d in devices])

    return _list_devices


class _GetDeviceCapabilitiesArgs(BaseModel):
    room_id: int = Field(..., description="장치가 속한 방 ID")
    device: str = Field(..., description="장치 이름(부분 일치, 예: '거실 조명')")


def make_get_device_capabilities_tool(user_id: int) -> BaseTool:
    @tool("get_device_capabilities", args_schema=_GetDeviceCapabilitiesArgs)
    async def _get_device_capabilities(room_id: int, device: str) -> str:
        """장치 이름으로 실행 가능한 action/query 목록(paramsSchema 포함)을 조회합니다.
        control_device/query_device 호출 전에 사용 가능한 이름을 확인할 때 씁니다."""
        device_id = await devices_internal.resolve_device_id(room_id, device, user_id=user_id)
        detail = await devices_internal.get_device(device_id)
        return _to_json(detail.model_dump(by_alias=True))

    return _get_device_capabilities


class _ControlDeviceArgs(BaseModel):
    room_id: int = Field(..., description="장치가 속한 방 ID")
    device: str = Field(..., description="장치 이름(부분 일치, 예: '거실 조명')")
    action: str = Field(..., description="실행할 action 이름 (get_device_capabilities 결과 참고)")
    params: dict[str, Any] = Field(default_factory=dict, description="action params")
    exec_mode: ExecMode = Field("once", description="once|repeat|toggle")


def make_control_device_tool(user_id: int) -> BaseTool:
    @tool("control_device", args_schema=_ControlDeviceArgs)
    async def _control_device(
        room_id: int, device: str, action: str, params: Optional[dict[str, Any]] = None, exec_mode: ExecMode = "once"
    ) -> str:
        """장치의 action(전원, 밝기 등)을 즉시 실행합니다."""
        device_id = await devices_internal.resolve_device_id(room_id, device, user_id=user_id)
        result = await devices_internal.invoke_device_action(
            device_id,
            action,
            InvokeDeviceRequest(params=params or {}, execMode=exec_mode, triggeredBy=f"agent:chat:{user_id}"),
        )
        return _to_json(result.model_dump())

    return _control_device


class _QueryDeviceArgs(BaseModel):
    room_id: int = Field(..., description="장치가 속한 방 ID")
    device: str = Field(..., description="장치 이름(부분 일치)")
    query: str = Field(..., description="조회할 query 이름 (get_device_capabilities 결과 참고)")
    params: dict[str, Any] = Field(default_factory=dict)


def make_query_device_tool(user_id: int) -> BaseTool:
    @tool("query_device", args_schema=_QueryDeviceArgs)
    async def _query_device(room_id: int, device: str, query: str, params: Optional[dict[str, Any]] = None) -> str:
        """장치의 실시간 센서·상태 값 하나를 조회합니다(예: power, brightness, state)."""
        device_id = await devices_internal.resolve_device_id(room_id, device, user_id=user_id)
        result = await devices_internal.query_device(device_id, query, QueryDeviceRequest(params=params or {}))
        return _to_json(result.model_dump())

    return _query_device


class _GetDeviceStateArgs(BaseModel):
    room_id: int = Field(..., description="장치가 속한 방 ID")
    device: str = Field(..., description="장치 이름(부분 일치)")


def make_get_device_state_tool(user_id: int) -> BaseTool:
    @tool("get_device_state", args_schema=_GetDeviceStateArgs)
    async def _get_device_state(room_id: int, device: str) -> str:
        """장치의 전체 런타임 상태 스냅샷을 조회합니다."""
        device_id = await devices_internal.resolve_device_id(room_id, device, user_id=user_id)
        state = await devices_internal.get_device_state(device_id)
        return _to_json(state.model_dump())

    return _get_device_state


class _ScheduleDeviceActionArgs(BaseModel):
    room_id: int = Field(..., description="장치가 속한 방 ID")
    device: str = Field(..., description="장치 이름(부분 일치)")
    action: str = Field(..., description="지연/반복 시 실행할 action 이름")
    schedule: RuleSchedule = Field(..., description='예: {"repeat":"once","delayMinutes":30}')
    params: dict[str, Any] = Field(default_factory=dict)
    name: Optional[str] = Field(None, description="예약 이름(생략 시 자동 생성)")


def make_schedule_device_action_tool(user_id: int) -> BaseTool:
    @tool("schedule_device_action", args_schema=_ScheduleDeviceActionArgs)
    async def _schedule_device_action(
        room_id: int,
        device: str,
        action: str,
        schedule: RuleSchedule,
        params: Optional[dict[str, Any]] = None,
        name: Optional[str] = None,
    ) -> str:
        """장치 동작을 지연 또는 반복 실행되도록 예약합니다."""
        device_id = await devices_internal.resolve_device_id(room_id, device, user_id=user_id)
        req = CreateRuleRequest(
            name=name or f"{device} {action} 예약",
            action=RuleAction(deviceId=device_id, name=action, params=params or {}),
            schedule=schedule,
        )
        rule = await rules_internal.create_rule(req)
        return _to_json(rule.model_dump())

    return _schedule_device_action


class _ListSchedulesArgs(BaseModel):
    room_id: Optional[int] = Field(None, description="특정 방의 예약만 (생략 시 전체)")
    enabled: Optional[bool] = Field(None, description="활성 예약만 필터링")


def make_list_schedules_tool(user_id: int) -> BaseTool:
    @tool("list_schedules", args_schema=_ListSchedulesArgs)
    async def _list_schedules(room_id: Optional[int] = None, enabled: Optional[bool] = None) -> str:
        """등록된 장치 예약(스케줄 룰) 목록을 조회합니다."""
        rules = await rules_internal.list_rules(enabled=enabled, has_schedule=True)
        if room_id is not None:
            room_devices = await devices_internal.list_devices(user_id=user_id, room_id=room_id)
            room_device_ids = {d.id for d in room_devices}
            rules = [r for r in rules if r.action.deviceId in room_device_ids]
        return _to_json([r.model_dump() for r in rules])

    return _list_schedules


class _CancelScheduleArgs(BaseModel):
    rule_id: str = Field(..., description="list_schedules 결과의 id")


def make_cancel_schedule_tool(user_id: int) -> BaseTool:
    @tool("cancel_schedule", args_schema=_CancelScheduleArgs)
    async def _cancel_schedule(rule_id: str) -> str:
        """등록된 장치 예약을 취소합니다."""
        await rules_internal.delete_rule(rule_id)
        return _to_json({"ok": True, "ruleId": rule_id})

    return _cancel_schedule


class _GetRoutineTasksArgs(BaseModel):
    day_of_week: Optional[str] = Field(None, description="'mon'..'sun'. 반복 루틴 조회용")
    date: Optional[str] = Field(None, description="'YYYY-MM-DD'. 해당 날짜의 1회성 일정도 함께 조회")


def make_get_routine_tasks_tool(user_id: int) -> BaseTool:
    @tool("get_routine_tasks", args_schema=_GetRoutineTasksArgs)
    async def _get_routine_tasks(day_of_week: Optional[str] = None, date: Optional[str] = None) -> str:
        """사용자의 반복 루틴과 1회성 일정을 조회합니다."""
        tasks = await get_routine_tasks(user_id, day_of_week, date)
        return _to_json(tasks)

    return _get_routine_tasks


class _UpdateRoutineTaskArgs(BaseModel):
    task_id: int = Field(..., description="get_routine_tasks 결과의 id")
    type: Literal["routine", "event"] = Field(..., description="get_routine_tasks 결과의 type과 동일해야 함")
    reason: str = Field(..., description="이 변경을 실행하는 이유(사용자 요청 요약)")
    day_of_week: Optional[str] = Field(None, description="type='routine'일 때 변경할 요일")
    date: Optional[str] = Field(None, description="type='event'일 때 변경할 날짜")
    start_minute: Optional[int] = Field(None, description="자정 기준 시작 분(0~1440)")
    end_minute: Optional[int] = Field(None, description="자정 기준 종료 분(0~1440)")


def make_update_routine_task_tool(user_id: int) -> BaseTool:
    @tool("update_routine_task", args_schema=_UpdateRoutineTaskArgs)
    async def _update_routine_task(
        task_id: int,
        type: Literal["routine", "event"],
        reason: str,
        day_of_week: Optional[str] = None,
        date: Optional[str] = None,
        start_minute: Optional[int] = None,
        end_minute: Optional[int] = None,
    ) -> str:
        """반복 루틴 또는 1회성 일정의 요일/날짜/시간을 변경합니다."""
        fields: dict[str, Any] = {}
        if day_of_week is not None:
            fields["dayOfWeek"] = day_of_week
        if date is not None:
            fields["date"] = date
        if start_minute is not None:
            fields["startMinute"] = start_minute
        if end_minute is not None:
            fields["endMinute"] = end_minute
        result = await update_routine_task(task_id, type, reason, **fields)
        return _to_json(result)

    return _update_routine_task


def build_tools(user_id: int) -> list[BaseTool]:
    return [
        make_query_db_tool(user_id),
        make_rag_search_tool(),
        make_list_devices_tool(user_id),
        make_get_device_capabilities_tool(user_id),
        make_control_device_tool(user_id),
        make_query_device_tool(user_id),
        make_get_device_state_tool(user_id),
        make_schedule_device_action_tool(user_id),
        make_list_schedules_tool(user_id),
        make_cancel_schedule_tool(user_id),
        make_get_routine_tasks_tool(user_id),
        make_update_routine_task_tool(user_id),
    ]


def _to_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)
