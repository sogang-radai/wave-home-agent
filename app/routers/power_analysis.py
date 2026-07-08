from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.schemas.jobs import JobRef
from app.schemas.power_analysis import PowerReportRequest
from app.services.job_common import get_job_or_404, job_response
from app.services.power_analysis import REPORT_KIND, create_report_job


router = APIRouter(prefix="/power/v1", tags=["power-analysis"])


@router.post("/reports", response_model=JobRef, status_code=202)
async def create_report(body: PowerReportRequest) -> JobRef:
    return create_report_job(body)


@router.get("/jobs/{job_id}")
async def get_job(job_id: str) -> JSONResponse:
    return job_response(get_job_or_404(job_id, kinds={REPORT_KIND}))
