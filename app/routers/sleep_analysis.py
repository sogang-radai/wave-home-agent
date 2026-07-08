from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.schemas.jobs import JobRef
from app.schemas.sleep_analysis import SleepReportRequest, SleepSummaryRequest
from app.services.job_common import get_job_or_404, job_response
from app.services.sleep_analysis import REPORT_KIND, SUMMARY_KIND, create_report_job, create_summary_job


router = APIRouter(prefix="/sleep/v1", tags=["sleep-analysis"])


@router.post("/summaries", response_model=JobRef, status_code=202)
async def create_summary(body: SleepSummaryRequest) -> JobRef:
    return create_summary_job(body)


@router.post("/reports", response_model=JobRef, status_code=202)
async def create_report(body: SleepReportRequest) -> JobRef:
    return create_report_job(body)


@router.get("/jobs/{job_id}")
async def get_job(job_id: str) -> JSONResponse:
    return job_response(get_job_or_404(job_id, kinds={SUMMARY_KIND, REPORT_KIND}))
