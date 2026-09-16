from typing import Literal

from pydantic import BaseModel, Field


class ActivityCandidate(BaseModel):
    """
    A structured activity that VoyageAI may place
    into the final itinerary.
    """

    name: str

    category: str

    description: str

    # ---------------------------------------------
    # LOCATION
    # ---------------------------------------------

    latitude: float | None = Field(
        default=None,
        ge=-90,
        le=90,
    )

    longitude: float | None = Field(
        default=None,
        ge=-180,
        le=180,
    )

    # ---------------------------------------------
    # ACTIVITY TYPE
    # ---------------------------------------------

    environment: Literal[
        "indoor",
        "outdoor",
        "mixed",
        "unknown",
    ] = "unknown"

    # ---------------------------------------------
    # TIME
    # ---------------------------------------------

    estimated_duration_minutes: int | None = Field(
        default=None,
        ge=15,
        le=720,
    )

    # ---------------------------------------------
    # COST
    # ---------------------------------------------

    estimated_cost: float | None = Field(
        default=None,
        ge=0,
    )

    currency: str | None = None

    # ---------------------------------------------
    # USER PREFERENCE
    # ---------------------------------------------

    preference_score: float = Field(
        default=0.5,
        ge=0,
        le=1,
    )

    # ---------------------------------------------
    # WEATHER
    # ---------------------------------------------

    weather_sensitive: bool = False

    # ---------------------------------------------
    # EVIDENCE
    # ---------------------------------------------

    source_ids: list[int] = Field(
        default_factory=list,
    )

    confidence: float = Field(
        default=0.5,
        ge=0,
        le=1,
    )


class ActivityIntelligence(BaseModel):
    """
    Collection of structured activity candidates
    for a destination.
    """

    destination: str

    activities: list[ActivityCandidate] = Field(
        default_factory=list,
    )