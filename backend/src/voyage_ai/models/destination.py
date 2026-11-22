from pydantic import BaseModel, Field


class DestinationRecommendation(BaseModel):
    name: str

    category: str

    why_recommended: str

    # An AI planning estimate of time a visitor might spend at the place.
    # This is not a sourced opening-hours or official visit-duration fact.
    estimated_visit_minutes: int | None = Field(default=None, ge=15, le=600)

    source_ids: list[int] = Field(
        min_length=1,
    )


class DestinationAnalysis(BaseModel):
    destination: str

    summary: str

    recommendations: list[DestinationRecommendation]

    practical_tips: list[str] = Field(
        default_factory=list,
    )


class ResearchSource(BaseModel):
    id: int
    title: str
    url: str


class DestinationResearch(BaseModel):
    destination: str

    summary: str

    recommendations: list[DestinationRecommendation]

    practical_tips: list[str]

    sources: list[ResearchSource]
