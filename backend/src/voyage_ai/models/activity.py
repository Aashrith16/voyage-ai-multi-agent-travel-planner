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
    resolved_place_category: str | None = None
    resolved_place_type: str | None = None

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
    duration_estimate_basis: Literal[
        "activity_specific_ai_estimate",
        "category_fallback_estimate",
    ] = "category_fallback_estimate"

    # ---------------------------------------------
    # COST
    # ---------------------------------------------

    estimated_cost: float | None = Field(
        default=None,
        ge=0,
    )

    currency: str | None = None
    cost_status: Literal["indicative", "user_provided", "unavailable", "verified_free"] = "unavailable"
    admission_status: Literal["verified_free", "priced", "unpriced"] = "unpriced"
    cost_basis: Literal["per_traveler", "per_group"] = "per_traveler"
    cost_source_url: str | None = None
    cost_source_type: Literal["official", "third_party", "unknown"] = "unknown"
    cost_retrieved_on: str | None = None
    cost_confidence: float | None = Field(default=None, ge=0, le=1)
    cost_confidence_level: Literal["low", "medium", "high"] | None = None
    cost_evidence: str | None = None
    opening_hours: str | None = None
    opening_hours_verified: bool = False

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
    excluded_accommodation_names: list[str] = Field(default_factory=list)
