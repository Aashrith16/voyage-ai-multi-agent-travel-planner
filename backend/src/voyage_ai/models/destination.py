from pydantic import BaseModel, Field


class DestinationRecommendation(BaseModel):
    name: str

    category: str

    why_recommended: str

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