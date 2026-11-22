from typing import Literal, TypedDict

from voyage_ai.models.activity import ActivityIntelligence
from voyage_ai.models.routing import TravelMatrix
from voyage_ai.models.itinerary import OptimizedItinerary

from voyage_ai.models.destination import DestinationResearch
from voyage_ai.models.trip import (
    TripRequest,
    TripRequestDraft,
)
from voyage_ai.models.weather import WeatherContext
from voyage_ai.models.budget import BudgetAllocation, BudgetCostEstimate
from voyage_ai.models.cost_research import CostResearchResult

class TravelRequestState(TypedDict, total=False):
    """
    Information that moves through the travel-request graph.
    """

    # Original message from the user
    user_input: str

    # Latest follow-up answer from the user
    followup_input: str

    # Combined travel information collected so far
    draft: TripRequestDraft

    # Questions VoyageAI needs to ask
    clarification_questions: list[str]

    # Strict final request after all information exists
    final_trip: TripRequest

    destination_research: DestinationResearch
    
    weather_context: WeatherContext

    activity_intelligence: ActivityIntelligence

    travel_matrix: TravelMatrix

    optimized_itinerary: OptimizedItinerary

    budget_cost_estimates: list[BudgetCostEstimate]

    cost_research: CostResearchResult

    budget_allocation: BudgetAllocation

    budget_approved: bool
    # Current workflow status
    status: Literal[
        "processing",
        "needs_clarification",
        "gathering_context",
        "optimizing",
        "budget_review",
        "complete",
    ]
