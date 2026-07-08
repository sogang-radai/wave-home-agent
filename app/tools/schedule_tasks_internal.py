"""schedule-tasks-api.md 의 주간·1회 일정 CRUD(`/internal/v1/schedule-tasks`) 클라이언트.

구 `/internal/v1/routine-tasks`(`type: routine|event` discriminator) 계약을 대체한다.
문서 스펙: `scheduleKind: 'weekly'|'once'` 로 구분하고, weekly 행은 `eventDate` 가 NULL,
once 행만 `eventDate` 를 가진다. `GET` 응답은 봉투 없이 배열을 바로 반환한다(device-tool-api.md
의 {items,count} 봉투와 다름 — 주의).
"""

from datetime import datetime, timezone
from typing import Any, Literal, Optional

from pydantic import BaseModel

from app.clients.core import CoreApiClient, ToolError
from app.config import get_settings
from app.tools.errors import InternalApiError


ScheduleKind = Literal["weekly", "once"]
DayOfWeek = Literal["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
CreatedBy = Literal["user", "agent"]


class ScheduleTask(BaseModel):
    id: int
    userId: int
    title: str
    createdAt: Optional[str] = None
    createdBy: CreatedBy = "agent"
    category: str
    scheduleKind: ScheduleKind
    dayOfWeek: DayOfWeek
    eventDate: Optional[str] = None
    startMinute: Optional[int] = None
    endMinute: Optional[int] = None
    done: bool = False
    sourceInsightId: Optional[int] = None


class CreateScheduleTaskRequest(BaseModel):
    userId: int
    title: str
    category: str
    scheduleKind: ScheduleKind = "weekly"
    dayOfWeek: DayOfWeek
    eventDate: Optional[str] = None
    startMinute: Optional[int] = None
    endMinute: Optional[int] = None


def _now_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _client() -> CoreApiClient:
    return CoreApiClient(base_url=get_settings().wavehome_agent_internal_base_url)


def _raise_from_tool_error(exc: ToolError) -> None:
    raise InternalApiError(exc.code or "CORE_API_UNAVAILABLE", str(exc), detail=exc.detail) from exc


# ── mock 상태 (WAVEHOME_CORE_API_MOCK=true) ─────────────────────────────────

_MOCK_SCHEDULE_TASKS: list[ScheduleTask] = [
    ScheduleTask(
        id=501,
        userId=1,
        title="운동",
        createdAt="2026-06-01 09:00:00",
        createdBy="user",
        category="exercise",
        scheduleKind="weekly",
        dayOfWeek="mon",
        eventDate=None,
        startMinute=1260,
        endMinute=1290,
        done=False,
    ),
    ScheduleTask(
        id=502,
        userId=1,
        title="병원 예약",
        createdAt="2026-06-20 09:00:00",
        createdBy="user",
        category="posture",
        scheduleKind="once",
        dayOfWeek="mon",
        eventDate="2026-07-14",
        startMinute=1140,
        endMinute=1170,
        done=False,
    ),
]

_next_mock_id = 503


async def get_schedule_tasks(
    user_id: int,
    *,
    day_of_week: Optional[str] = None,
    event_date: Optional[str] = None,
    schedule_kind: Optional[ScheduleKind] = None,
    from_: Optional[str] = None,
    to: Optional[str] = None,
    done: Optional[bool] = None,
) -> list[ScheduleTask]:
    client = _client()
    if client.is_mock:
        items = [t for t in _MOCK_SCHEDULE_TASKS if t.userId == user_id]
        if day_of_week is not None:
            items = [t for t in items if t.dayOfWeek == day_of_week]
        if event_date is not None:
            items = [t for t in items if t.eventDate == event_date]
        if schedule_kind is not None:
            items = [t for t in items if t.scheduleKind == schedule_kind]
        if done is not None:
            items = [t for t in items if t.done == done]
        if from_ is not None:
            items = [t for t in items if t.eventDate is not None and t.eventDate >= from_]
        if to is not None:
            items = [t for t in items if t.eventDate is not None and t.eventDate < to]
        return items

    params = {
        k: v
        for k, v in {
            "userId": user_id,
            "dayOfWeek": day_of_week,
            "eventDate": event_date,
            "scheduleKind": schedule_kind,
            "from": from_,
            "to": to,
            "done": done,
        }.items()
        if v is not None
    }
    try:
        response = await client.get("/schedule-tasks", params)
    except ToolError as exc:
        _raise_from_tool_error(exc)
    return [ScheduleTask.model_validate(item) for item in response]


async def create_schedule_task(req: CreateScheduleTaskRequest) -> ScheduleTask:
    client = _client()
    if client.is_mock:
        global _next_mock_id
        task = ScheduleTask(
            id=_next_mock_id,
            createdAt=_now_str(),
            createdBy="agent",
            **req.model_dump(),
        )
        _next_mock_id += 1
        _MOCK_SCHEDULE_TASKS.append(task)
        return task

    try:
        response = await client.post("/schedule-tasks", json=req.model_dump(exclude_none=True))
    except ToolError as exc:
        _raise_from_tool_error(exc)
    return ScheduleTask.model_validate(response)


async def update_schedule_task(task_id: int, user_id: int, **fields: Any) -> ScheduleTask:
    client = _client()
    if client.is_mock:
        for idx, task in enumerate(_MOCK_SCHEDULE_TASKS):
            if task.id == task_id and task.userId == user_id:
                updated = task.model_copy(update=fields)
                _MOCK_SCHEDULE_TASKS[idx] = updated
                return updated
        raise InternalApiError("NOT_FOUND", f"id={task_id} 인 일정을 찾을 수 없습니다.")

    try:
        response = await client.patch(f"/schedule-tasks/{task_id}", json=fields)
    except ToolError as exc:
        _raise_from_tool_error(exc)
    return ScheduleTask.model_validate(response)


async def delete_schedule_task(task_id: int, user_id: int) -> int:
    client = _client()
    if client.is_mock:
        before = len(_MOCK_SCHEDULE_TASKS)
        _MOCK_SCHEDULE_TASKS[:] = [
            t for t in _MOCK_SCHEDULE_TASKS if not (t.id == task_id and t.userId == user_id)
        ]
        if len(_MOCK_SCHEDULE_TASKS) == before:
            raise InternalApiError("NOT_FOUND", f"id={task_id} 인 일정을 찾을 수 없습니다.")
        return task_id

    try:
        response = await client.delete(f"/schedule-tasks/{task_id}")
    except ToolError as exc:
        _raise_from_tool_error(exc)
    return int(response["id"])
