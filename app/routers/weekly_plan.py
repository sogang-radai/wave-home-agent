from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.schemas.jobs import JobRef
from app.schemas.weekly_plan import WeeklyPlanReportRequest
from app.services.job_common import get_job_or_404, job_response
from app.services.weekly_plan import REPORT_KIND, create_report_job


router = APIRouter(prefix="/weekly-plan/v1", tags=["weekly-plan-analysis"])


@router.post("/reports", response_model=JobRef, status_code=202)
async def create_report(body: WeeklyPlanReportRequest) -> JobRef:
    return create_report_job(body)


@router.get("/jobs/{job_id}")
async def get_job(job_id: str) -> JSONResponse:
    return job_response(get_job_or_404(job_id, kinds={REPORT_KIND}))
