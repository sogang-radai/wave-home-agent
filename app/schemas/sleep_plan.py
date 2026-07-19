"""'오늘 밤 추천 수면 시간' 기능의 agent 쪽 요청/응답 스키마.

취침/기상 시각 산정은 전적으로 에이전트가 담당한다(C++ 백엔드는 sleep_plan 테이블에
캐싱된 값을 읽기만 하고 직접 계산하지 않는다 - service/sleep_plan_generator.cpp 참고).
sleep/reports API(SleepReportRequest)와 동일한 패턴으로, 필요한 데이터(최근 sleep_session,
오늘·내일 schedule_task)는 C++ 가 미리 조회해 payload 에 인라인으로 담아 보낸다 - 에이전트가
gather 단계에서 db/query 툴로 스스로 조회하지 않는다(왕복이 늘어나고, LLM이 조회를 스킵할
수도 있어 데이터가 항상 보장되지 않았다).

C++ 쪽 runSleepJobSync() 는 GET /sleep/v1/jobs/{job_id} 의 result.reportText 를
평문 string 으로만 이해하므로(app/routers/sleep_analysis.py 참고), SleepPlanResult.reportText
에는 SleepPlanContent 를 json.dumps 한 문자열을 담아 그 평문 계약 위에 구조화된 값을 실어 보낸다.
"""

from typing import Optional

from pydantic import BaseModel, Field

from app.schemas.sleep_analysis import SleepSessionRow
from app.tools.schedule_tasks_internal import ScheduleTask


class SleepPlanRequest(BaseModel):
    userId: int
    planDate: str  # 'YYYY-MM-DD', 이 계획이 적용되는 밤
    sessions: list[SleepSessionRow] = Field(default_factory=list)  # 최근 7일 sleep_session
    todaySchedule: list[ScheduleTask] = Field(default_factory=list)  # planDate 당일 일정
    tomorrowSchedule: list[ScheduleTask] = Field(default_factory=list)  # planDate 다음날 일정(기상 제약 판단용)
    embed: bool = False


class SleepPlanContent(BaseModel):
    bedtimeMinute: int  # 자정 기준 분(0~1439)
    wakeMinute: int  # 자정 기준 분(0~1439)
    prepMinute: Optional[int] = None
    recommendedTempC: Optional[float] = None
    targetDurationMinutes: int
    rationale: str  # 1~2문장, 한국어


class SleepPlanResult(BaseModel):
    planDate: str
    reportText: str  # json.dumps(SleepPlanContent.model_dump()) — 위 통합 제약 참고
    embedding: Optional[list[float]] = None
