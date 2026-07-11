from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.schemas.goal_coaching import GoalCoachingRequest
from app.schemas.jobs import JobRef
from app.services.goal_coaching import GOAL_COACHING_KIND, create_report_job
from app.services.job_common import get_job_or_404, job_response


router = APIRouter(prefix="/goal-coaching/v1", tags=["goal-coaching"])


@router.post("/reports", response_model=JobRef, status_code=202)
async def create_report(body: GoalCoachingRequest) -> JobRef:
    return create_report_job(body)


@router.get("/jobs/{job_id}")
async def get_job(job_id: str) -> JSONResponse:
    return job_response(get_job_or_404(job_id, kinds={GOAL_COACHING_KIND}))
