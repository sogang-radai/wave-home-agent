"""Shared response type for docs/api.md §1.4's POST endpoints (sleep + power).
GET /jobs/{jobId} is intentionally untyped (response_model=None) in the routers
since its shape varies by status (queued/running/done/failed) — see
app/routers/sleep_analysis.py and app/routers/power_analysis.py."""

from typing import Literal

from pydantic import BaseModel


class JobRef(BaseModel):
    jobId: str
    status: Literal["queued"] = "queued"
