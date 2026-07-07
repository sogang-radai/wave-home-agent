from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.errors import AgentApiError
from app.schemas.jobs import JobRef
from app.schemas.sleep_analysis import SleepReportRequest, SleepSummaryRequest
from app.services.jobs import job_store
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
    job = job_store.get(job_id, kinds={SUMMARY_KIND, REPORT_KIND})
    if job is None:
        raise AgentApiError(404, "JOB_NOT_FOUND", "jobId 에 해당하는 작업이 없습니다.")

    payload = {"jobId": job.job_id, "status": job.status}
    if job.result is not None:
        payload["result"] = job.result
    if job.error is not None:
        payload["error"] = job.error
    return JSONResponse(content=payload)
