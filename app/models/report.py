from pydantic import BaseModel, Field


class ReportDraft(BaseModel):
    title: str
    summary: str = ""
    highlights: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
