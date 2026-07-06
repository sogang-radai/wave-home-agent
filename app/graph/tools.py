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

from app.tools.db_query import DbQuery, query_db
from app.tools.devices_internal import control_device, list_devices
from app.tools.rag_search import RagTarget, rag_search
from app.tools.routine_tasks_internal import get_routine_tasks, update_routine_task


class _QueryDbArgs(BaseModel):
    queries: list[DbQuery] = Field(..., description="최대 10개의 배치 조회. api.md §2.1 참고.")


def make_query_db_tool(user_id: int) -> BaseTool:
    @tool("query_db", args_schema=_QueryDbArgs)
    async def _query_db(queries: list[DbQuery]) -> str:
        """정확한 최신 값이 필요할 때 사용하세요: 특정 날짜의 수면 세션/통계, 오늘 일정, 정확한 점수/시간 등
        구조화된 raw row를 조회합니다. "어젯밤", "오늘", "정확히 몇 점" 같은 질문에 적합합니다.
        userId 필터는 항상 현재 사용자로 고정됩니다."""
        for q in queries:
            if "userId" in q.filter:
                q.filter["userId"] = user_id
        results = await query_db(queries)
        return _to_json([r.model_dump() for r in results])

    return _query_db


class _RagSearchArgs(BaseModel):
    query: str = Field(..., description="검색할 자연어 질의")
    targets: list[RagTarget] = Field(..., description="검색 대상 컬렉션 목록. api.md §2.6 참고.")


def make_rag_search_tool() -> BaseTool:
    @tool("rag_search", args_schema=_RagSearchArgs)
    async def _rag_search(query: str, targets: list[RagTarget]) -> str:
        """과거에 만들어진 자연어 요약(리포트 문장, 기간별 패턴 설명)을 의미 기반으로 검색합니다.
        "요즘", "최근", "패턴", "이전보다", "왜 그런지" 같은 장기 맥락·비교·원인 질문에 적합합니다.
        정확한 최신 수치가 필요하면 query_db를 대신 쓰세요."""
        results = await rag_search(query, targets)
        return _to_json([r.model_dump() for r in results])

    return _rag_search


class _ListDevicesArgs(BaseModel):
    room_id: int = Field(..., description="조회할 방 ID")


def make_list_devices_tool(user_id: int) -> BaseTool:
    @tool("list_devices", args_schema=_ListDevicesArgs)
    async def _list_devices(room_id: int) -> str:
        """방에 속한 가전 기기와 현재 제어값을 조회합니다."""
        devices = await list_devices(room_id, user_id)
        return _to_json(devices)

    return _list_devices


class _ControlDeviceArgs(BaseModel):
    device_id: int = Field(..., description="제어할 기기 ID (list_devices 결과의 id)")
    control_id: int = Field(..., description="제어 항목 ID (list_devices 결과의 controls[].id)")
    value: Any = Field(..., description="설정할 값")
    reason: str = Field(..., description="이 제어를 실행하는 이유(사용자 요청 요약)")


def make_control_device_tool(user_id: int) -> BaseTool:
    @tool("control_device", args_schema=_ControlDeviceArgs)
    async def _control_device(device_id: int, control_id: int, value: Any, reason: str) -> str:
        """기기의 제어 항목(온도, 전원 등)을 실행합니다."""
        result = await control_device(device_id, control_id, value, user_id, reason)
        return _to_json(result)

    return _control_device


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
        make_control_device_tool(user_id),
        make_get_routine_tasks_tool(user_id),
        make_update_routine_task_tool(user_id),
    ]


def _to_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)
