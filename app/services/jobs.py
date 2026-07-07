"""In-memory async job store backing docs/api.md §1.4 (Sleep/Power Analysis API).

This server never touches SQLite directly (see README.md), so job state can't be
persisted — it lives only in process memory and is lost on restart. That's an
accepted limitation at this stage (see docs/api.md §7 TODO).
"""

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Literal, Optional


logger = logging.getLogger(__name__)

JobStatus = Literal["queued", "running", "done", "failed"]

_RETENTION = timedelta(hours=24)


@dataclass
class Job:
    job_id: str
    kind: str
    dedupe_key: str
    status: JobStatus = "queued"
    result: Optional[dict[str, Any]] = None
    error: Optional[dict[str, Any]] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    finished_at: Optional[datetime] = None


class JobAlreadyRunning(Exception):
    """Raised by JobStore.create when dedupe_key already has a queued/running job."""

    def __init__(self, existing_job_id: str) -> None:
        super().__init__(f"job already running for this target: {existing_job_id}")
        self.existing_job_id = existing_job_id


class JobStore:
    """Single shared in-memory registry for all job kinds (sleep_summary, sleep_report,
    power_report). asyncio is single-threaded and none of these methods await, so
    check-then-write here is atomic without a lock."""

    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._active_by_key: dict[str, str] = {}

    def create(self, kind: str, dedupe_key: str) -> Job:
        existing_id = self._active_by_key.get(dedupe_key)
        if existing_id is not None:
            logger.info(
                "[JOB REJECTED] %-13s target=%-40s already running as %s",
                kind, dedupe_key, existing_id,
            )
            raise JobAlreadyRunning(existing_id)

        job = Job(job_id=f"job_{uuid.uuid4().hex}", kind=kind, dedupe_key=dedupe_key)
        self._jobs[job.job_id] = job
        self._active_by_key[dedupe_key] = job.job_id
        logger.info(
            "[JOB QUEUED]   %-13s target=%-40s id=%s | %d job(s) now queued/running",
            kind, dedupe_key, job.job_id, len(self._active_by_key),
        )
        return job

    def mark_running(self, job_id: str) -> None:
        job = self._jobs[job_id]
        job.status = "running"
        logger.info("[JOB RUNNING]  %-13s target=%-40s id=%s", job.kind, job.dedupe_key, job_id)

    def complete(self, job_id: str, result: dict[str, Any]) -> None:
        job = self._jobs[job_id]
        job.status = "done"
        job.result = result
        job.finished_at = datetime.now(timezone.utc)
        self._active_by_key.pop(job.dedupe_key, None)
        elapsed = (job.finished_at - job.created_at).total_seconds()
        has_embedding = bool(result.get("embedding"))
        logger.info(
            "[JOB DONE]     %-13s target=%-40s id=%s | %.2fs | embedding=%s model=%s | %d job(s) still queued/running",
            job.kind, job.dedupe_key, job_id, elapsed,
            "yes" if has_embedding else "no", result.get("model"), len(self._active_by_key),
        )

    def fail(self, job_id: str, error: dict[str, Any]) -> None:
        job = self._jobs[job_id]
        job.status = "failed"
        job.error = error
        job.finished_at = datetime.now(timezone.utc)
        self._active_by_key.pop(job.dedupe_key, None)
        elapsed = (job.finished_at - job.created_at).total_seconds()
        logger.warning(
            "[JOB FAILED]   %-13s target=%-40s id=%s | %.2fs | %s | %d job(s) still queued/running",
            job.kind, job.dedupe_key, job_id, elapsed, error, len(self._active_by_key),
        )

    def get(self, job_id: str, kinds: set[str]) -> Optional[Job]:
        job = self._jobs.get(job_id)
        if job is None or job.kind not in kinds:
            return None
        if job.finished_at is not None and datetime.now(timezone.utc) - job.finished_at > _RETENTION:
            del self._jobs[job_id]
            return None
        return job


job_store = JobStore()
