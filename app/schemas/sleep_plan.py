"""'오늘 밤 추천 수면 시간' 기능의 agent 쪽 요청/응답 스키마.

C++ 백엔드의 GET /api/v1/sleep/today/plan 이 sleep_session/schedule_task 로부터
결정론적 추천값을 계산해 sleep_plan 테이블에 캐싱하는 것과는 별개로, 이 스키마는
그 캐시를 더 나은 자연어 근거(rationale)와 다듬어진 취침/기상 추천으로 보강하는
agent job(app/services/sleep_analysis.py의 PLAN_KIND)의 입출력을 정의한다.

C++ 쪽 runSleepJobSync() 는 GET /sleep/v1/jobs/{job_id} 의 result.reportText 를
평문 string 으로만 이해하므로(app/routers/sleep_analysis.py 참고), SleepPlanResult.reportText
에는 SleepPlanContent 를 json.dumps 한 문자열을 담아 그 평문 계약 위에 구조화된 값을 실어 보낸다.
"""

from typing import Optional

from pydantic import BaseModel


class SleepPlanRequest(BaseModel):
    userId: int
    planDate: str  # 'YYYY-MM-DD', 이 계획이 적용되는 밤
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
