"""goal-coaching 기능(신규) 비즈니스 로직: 목표 코칭 리포트 생성을 job 으로 처리한다.

app/services/job_common.py 의 공용 job 골격(create_job_or_409/spawn)을 insight/weekly_plan 과
동일하게 재사용한다. embed 는 항상 False 로 취급한다 - insight/weekly_plan 이전까지도
"실제 vec 저장소가 아직 없다"는 이유로 sleep/power 에만 임베딩을 붙였던 것과 같은 원칙이며,
이 요청 스키마(app/schemas/goal_coaching.py)의 embed 필드도 항상 false 로 호출된다는 전제라
apply_embedding 호출 자체를 넣지 않는다.
"""

import logging
import re

from app.graph.goal_coaching_graph import build as build_goal_coaching_graph
from app.schemas.goal_coaching import GoalCoachingRequest, GoalCoachingResult, GoalTitleJudgement
from app.schemas.jobs import JobRef
from app.services.job_common import create_job_or_409, spawn
from app.services.jobs import job_store
from app.services.llm import invoke_structured
from app.services.prompts import load_prompt


logger = logging.getLogger(__name__)

GOAL_COACHING_KIND = "goal_coaching_report"

_graph = build_goal_coaching_graph()

# LLM 부재/실패 시 쓰는 결정적 거절 목록(소문자·정규화 후 비교).
_MEANINGLESS_TITLES = {
    "안녕",
    "안녕하세요",
    "ㅎㅇ",
    "하이",
    "hi",
    "hello",
    "hey",
    "ㅎㅎ",
    "ㅋㅋ",
    "ㅋ",
    "ㅎ",
    "테스트",
    "test",
    "testing",
    "asdf",
    "asd",
    "aaa",
    "...",
    "…",
    "없음",
    "모름",
    "그냥",
}


def _normalize_title(title: str) -> str:
    return re.sub(r"\s+", "", title.strip().lower())


def _heuristic_title_judgement(title: str, category: str) -> GoalTitleJudgement:
    raw = title.strip()
    if len(raw) < 2:
        return GoalTitleJudgement(
            accept=False,
            reason="목표가 너무 짧아요. 지키려는 습관을 조금만 더 구체적으로 적어 주세요. 예: 취침 11시 전에 자기",
        )
    normalized = _normalize_title(raw)
    if normalized in _MEANINGLESS_TITLES or re.fullmatch(r"[.\-_=+~!@#$%^&*]+", raw):
        return GoalTitleJudgement(
            accept=False,
            reason=(
                f"「{raw}」는 습관 목표로 보기 어려워요. "
                f"{category} 카테고리에 맞는 행동을 적어 주세요. 예: 취침 11시 전에 자기"
            ),
        )
    return GoalTitleJudgement(accept=True, reason="")


async def judge_goal_title(title: str, category: str) -> GoalTitleJudgement:
    """목표 제목이 코칭 가능한 습관인지 판정. LLM 우선, 실패 시 휴리스틱."""
    fallback = _heuristic_title_judgement(title, category)
    prompt = load_prompt(
        "goal_coaching",
        "validate_title",
        goal_title=title.strip(),
        category=category,
    )
    return await invoke_structured(GoalTitleJudgement, prompt, fallback=fallback)


def create_report_job(body: GoalCoachingRequest) -> JobRef:
    dedupe_key = f"{GOAL_COACHING_KIND}:{body.goalId}:{body.periodStart}"
    job = create_job_or_409(GOAL_COACHING_KIND, dedupe_key=dedupe_key)
    spawn(_run_report(job.job_id, body), job_id=job.job_id)
    return JobRef(jobId=job.job_id)


async def _run_report(job_id: str, body: GoalCoachingRequest) -> None:
    job_store.mark_running(job_id)

    judgement = await judge_goal_title(body.goalTitle, body.category)
    if not judgement.accept:
        reason = (judgement.reason or "").strip() or (
            f"「{body.goalTitle.strip()}」는 습관 목표로 보기 어려워요. "
            "지키려는 행동을 조금 더 구체적으로 적어 주세요."
        )
        job_store.fail(job_id, {"code": "INVALID_GOAL", "message": reason})
        return

    result = await _graph.ainvoke(
        {
            "user_id": body.userId,
            "goal_id": body.goalId,
            "goal_title": body.goalTitle,
            "category": body.category,
            "period_start": body.periodStart,
            "rounds": 0,
        }
    )
    content = result["content"]
    response = GoalCoachingResult(
        periodStart=body.periodStart,
        pastSummary=content.pastSummary,
        projection=content.projection,
        projectedMetrics=content.projectedMetrics,
        items=content.items,
    )
    job_store.complete(job_id, response.model_dump())
