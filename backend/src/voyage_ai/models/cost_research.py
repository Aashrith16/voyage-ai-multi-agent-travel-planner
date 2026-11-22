from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

from voyage_ai.models.budget import BudgetCostEstimate


CostResearchCategory = Literal[
    "transportation", "accommodation", "food_dining",
    "local_transportation", "activities_attractions",
]
CostRejectionReason = Literal[
    "irrelevant_source",
    "missing_amount",
    "missing_currency",
    "missing_cost_basis",
    "unsupported_currency",
    "ambiguous_price",
    "ambiguous_currency",
    "ambiguous_cost_basis",
    "ambiguous_fare_class",
    "ambiguous_accommodation_unit",
    "unspecified_attraction",
    "illustrative_example",
    "tax_amount",
]

CostStatementBasis = Literal[
    "per_person", "per_night", "per_person_per_night", "per_day",
    "per_person_per_day", "per_room_per_night", "per_capsule_per_night",
    "per_person_per_room_per_night", "per_ride", "per_admission", "per_trip",
]

CostEvidenceScope = Literal["category", "entity", "manual"]


class CostPriceStatement(BaseModel):
    """One price and the nearby wording that explains what it buys."""

    category: CostResearchCategory
    scope: CostEvidenceScope = "category"
    entity_name: str | None = None
    source_title: str = ""
    source_url: str = ""
    retrieved_on: date | None = None
    description: str
    amount_min: float
    amount_max: float
    currency: str | None = None
    basis: CostStatementBasis | None = None
    fare_class: Literal["adult", "child"] | None = None
    ticket_type: Literal["day_pass", "multi_day_pass", "single_ticket"] | None = None
    pass_duration_days: int | None = Field(default=None, ge=1)
    taxes_included: bool | None = None
    confidence_level: Literal["low", "medium", "high"] | None = None
    evidence_quote: str
    accepted: bool = False
    rejection_reasons: list[CostRejectionReason] = Field(default_factory=list)


class CostEvidenceOption(BaseModel):
    """A valid evidence item that can be explicitly selected at budget review."""

    option_id: str
    group_id: str
    label: str
    estimate: BudgetCostEstimate
    requires_confirmation: bool = True


class VerifiedFreeAdmissionEvidence(BaseModel):
    """Official, attraction-specific evidence that admission is free."""

    activity_name: str
    source_url: str
    evidence_quote: str
    retrieved_on: date


class CostOptionSelection(BaseModel):
    option_id: str
    traveler_count: int | None = Field(default=None, ge=1)
    quantity: int | None = Field(default=None, ge=1)


class CostResearchSource(BaseModel):
    title: str
    url: str
    retrieved_on: date
    excerpt: str
    snippet: str = ""
    page_text_excerpt: str = ""
    page_content_retrieved: bool = False
    source_type: Literal["official", "third_party", "unknown"] = "unknown"
    category: CostResearchCategory = "activities_attractions"
    relevant: bool = True
    rejection_reasons: list[CostRejectionReason] = Field(default_factory=list)
    queries: list[str] = Field(default_factory=list)
    categories: list[CostResearchCategory] = Field(default_factory=list)
    price_statements: list[CostPriceStatement] = Field(default_factory=list)


class CostResearchResult(BaseModel):
    status: Literal["available", "partial", "unavailable"]
    sources: list[CostResearchSource] = Field(default_factory=list)
    estimates: list[BudgetCostEstimate] = Field(default_factory=list)
    options: list[CostEvidenceOption] = Field(default_factory=list)
    verified_free_activities: list[VerifiedFreeAdmissionEvidence] = Field(default_factory=list)
    price_statements: list[CostPriceStatement] = Field(default_factory=list)
    search_errors: dict[str, str] = Field(default_factory=dict)
    note: str = ""
