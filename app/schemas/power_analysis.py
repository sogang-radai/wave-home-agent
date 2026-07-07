"""docs/api.md §1.4 Power Analysis API request/response types (teammate.md's
PowerEnergyRow/PowerReportRequest/PowerReportResponse)."""

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


PowerPeriod = Literal["1h", "24h", "1w", "1mo"]


class PowerEnergyRow(BaseModel):
    id: int
    deviceId: Optional[int] = None
    granularity: Literal["5m", "1h", "24h", "1w", "1mo"]
    timeStart: str
    energyWh: float
    coverage: float
    sampleCount: int


class PowerReportRequest(BaseModel):
    deviceId: Optional[int] = None
    period: PowerPeriod
    periodStart: str
    metrics: dict[str, Any]
    target: PowerEnergyRow
    children: Optional[list[PowerEnergyRow]] = Field(default_factory=list)
    embed: bool = True
    model: Optional[str] = None
    embeddingModel: Optional[str] = None


class PowerReportResponse(BaseModel):
    energyId: int
    period: PowerPeriod
    periodStart: str
    deviceId: Optional[int] = None
    reportText: str
    embedding: Optional[list[float]] = None
    model: str
    embeddingModel: Optional[str] = None
