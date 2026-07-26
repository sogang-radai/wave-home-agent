from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.schemas.banner import HabitBannerRequest
from app.schemas.habit import HabitBuilderRequest
from app.schemas.insight import InsightGenerationRequest
from app.schemas.jobs import JobRef
from app.services.banner import BANNER_KIND, create_banner_job
from app.services.habit import HABIT_KIND, create_habit_job
from app.services.insight import INSIGHT_KIND, create_insight_job
from app.services.job_common import get_job_or_404, job_response


router = APIRouter(prefix="/insight/v1", tags=["insight-generation"])


@router.post("/insights", response_model=JobRef, status_code=202)
async def create_insight(body: InsightGenerationRequest) -> JobRef:
    return create_insight_job(body)


@router.post("/habits", response_model=JobRef, status_code=202)
async def create_habit(body: HabitBuilderRequest) -> JobRef:
    # Shares this router's /jobs/{job_id} polling endpoint with insight
    # generation rather than standing up a separate job type — habit
    # discovery is called directly from the C++ backend's daily rollover
    # (no AgentJobQueue involved), same job-store/poll shape either way.
    return create_habit_job(body)


@router.post("/habit-banner", response_model=JobRef, status_code=202)
async def create_habit_banner(body: HabitBannerRequest) -> JobRef:
    return create_banner_job(body)


@router.get("/jobs/{job_id}")
async def get_job(job_id: str) -> JSONResponse:
    return job_response(get_job_or_404(job_id, kinds={INSIGHT_KIND, HABIT_KIND, BANNER_KIND}))
