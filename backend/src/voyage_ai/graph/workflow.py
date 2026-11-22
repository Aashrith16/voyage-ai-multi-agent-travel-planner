from typing import Literal
from math import isfinite
import logging
import re

from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from voyage_ai.agents.destination_agent import research_destination

from voyage_ai.services.weather_service import (
    get_weather_context,
    unavailable_weather_context,
)

from voyage_ai.services.activity_service import (
    build_activity_intelligence,
)

from voyage_ai.services.routing_service import (
    build_travel_matrix,
)

from voyage_ai.services.itinerary_optimizer import (
    optimize_itinerary,
)

from voyage_ai.agents.request_agent import (
    get_clarification_questions,
    understand_trip_request,
)
from voyage_ai.graph.state import TravelRequestState
from voyage_ai.models.budget import (
    BudgetAllocation,
    BudgetCategoryAllocation,
    BudgetCostEstimate,
)
from voyage_ai.models.cost_research import CostEvidenceOption, CostPriceStatement, CostResearchResult, CostResearchSource, VerifiedFreeAdmissionEvidence
from voyage_ai.services.cost_research_service import resolve_cost_option_selections
from voyage_ai.models.activity import ActivityCandidate, ActivityIntelligence
from voyage_ai.models.destination import (
    DestinationRecommendation,
    DestinationResearch,
    ResearchSource,
)
from voyage_ai.models.itinerary import (
    OptimizedDay,
    OptimizedItinerary,
    ScheduledActivity,
)
from voyage_ai.models.routing import TravelMatrix
from voyage_ai.models.trip import TripRequest, TripRequestDraft
from voyage_ai.models.weather import DailyWeather, WeatherContext, WeatherRisk
from voyage_ai.services.trip_request_service import (
    finalize_trip_request,
    is_trip_request_complete,
    merge_trip_drafts,
)
from voyage_ai.services.budget_service import (
    apply_budget_edits,
    build_budget_allocation,
)
from voyage_ai.services.cost_research_service import research_trip_costs
from voyage_ai.diagnostics import instrument_workflow_node
from voyage_ai.persistence import initialize_database

logger = logging.getLogger(__name__)


# --------------------------------------------------
# NODE 1
# Understand the user's FIRST message
# --------------------------------------------------

def understand_request_node(
    state: TravelRequestState,
) -> dict:

    user_input = state["user_input"]

    draft = understand_trip_request(
        user_input
    )

    return {
        "draft": draft,
        "status": "processing",
    }


# --------------------------------------------------
# ROUTER
# Decide whether we need clarification
# --------------------------------------------------

def route_request(
    state: TravelRequestState,
) -> Literal["clarify", "finalize"]:

    draft = state["draft"]

    if is_trip_request_complete(draft):
        return "finalize"

    return "clarify"


# --------------------------------------------------
# NODE 2
# Ask the user for missing information
# AND PAUSE THE GRAPH
# --------------------------------------------------

def clarification_node(
    state: TravelRequestState,
) -> dict:

    draft = state["draft"]

    questions = get_clarification_questions(
        draft
    )

    # interrupt() pauses LangGraph here.
    #
    # The graph waits until somebody resumes
    # it with Command(resume=...).
    user_reply = interrupt(
        {
            "message": "More trip information is required.",
            "questions": questions,
        }
    )

    return {
        "clarification_questions": questions,
        "followup_input": user_reply,
        "status": "processing",
    }


# --------------------------------------------------
# NODE 3
# Understand the user's FOLLOW-UP answer
# and merge it with the previous state
# --------------------------------------------------
def process_followup_node(
    state: TravelRequestState,
) -> dict:

    previous_draft = state["draft"]

    followup_input = state[
        "followup_input"
    ].strip()

    

    # If destination is already known but origin is missing,
    # treat the clarification answer as the origin.
    if (
        previous_draft.destination
        and not previous_draft.origin
    ):
        merged_draft = previous_draft.model_copy(
            update={
                "origin": followup_input,
            }
        )

       
        return {
            "draft": merged_draft,
            "status": "processing",
        }

    # Fallback for any other clarification.
    new_draft = understand_trip_request(
        followup_input
    )

    merged_draft = merge_trip_drafts(
        previous_draft,
        new_draft,
    )

    return {
        "draft": merged_draft,
        "status": "processing",
    }
# --------------------------------------------------
# NODE 4
# Create strict final TripRequest
# --------------------------------------------------

def finalize_request_node(
    state: TravelRequestState,
) -> dict:

    draft = state["draft"]

    final_trip = finalize_trip_request(
        draft
    )

    return {
        "final_trip": final_trip,
        "status": "gathering_context",
    }

# --------------------------------------------------
# NODE 5
# Research the completed destination
# --------------------------------------------------

def research_destination_node(
    state: TravelRequestState,
) -> dict:

    final_trip = state["final_trip"]

    research = research_destination(
        final_trip
    )

    return {
        "destination_research": research,
    }

# ==================================================
# WEATHER INTELLIGENCE NODE
# ==================================================

def weather_intelligence_node(
    state: TravelRequestState,
) -> dict:

    final_trip = state["final_trip"]

    try:
        weather_context = get_weather_context(
            destination=final_trip.destination,
            start_date=final_trip.departure_date,
            end_date=final_trip.return_date,
        )
    except Exception as error:
        # Weather is optional planning context. A last-resort failure must not
        # prevent research, budget review, or itinerary generation.
        logger.warning(
            "Weather unavailable; continuing without conditions (exception_type=%s)",
            type(error).__name__,
        )
        weather_context = unavailable_weather_context(
            destination=final_trip.destination,
            start_date=final_trip.departure_date,
            end_date=final_trip.return_date,
            error=error,
        )

    return {
        "weather_context": weather_context,
    }

# ==================================================
# CONTEXT JOIN NODE
# ==================================================

def context_ready_node(
    state: TravelRequestState,
) -> dict:

    if "destination_research" not in state:
        raise ValueError(
            "Destination research is missing."
        )

    if "weather_context" not in state:
        raise ValueError(
            "Weather context is missing."
        )

    return {
        "status": "optimizing",
    }

# ==================================================
# ACTIVITY INTELLIGENCE NODE
# ==================================================

def activity_intelligence_node(
    state: TravelRequestState,
) -> dict:

    trip = state["final_trip"]

    research = state[
        "destination_research"
    ]

    activity_intelligence = (
        build_activity_intelligence(
            trip=trip,
            research=research,
        )
    )

    activity_intelligence = (
        add_planning_durations(
            activity_intelligence
        )
    )

    return {
        "activity_intelligence":
            activity_intelligence,
    }

# ==================================================
# PLANNING DURATION ASSUMPTIONS
#
# These are scheduling assumptions only.
# They are NOT official attraction visit durations.
# ==================================================

def add_planning_durations(
    intelligence,
):

    enriched = []

    for activity in intelligence.activities:

        if (
            activity.estimated_duration_minutes
            is not None
        ):
            enriched.append(activity)
            continue

        category = activity.category.lower()

        if any(
            word in category
            for word in [
                "park",
                "garden",
                "walking",
            ]
        ):
            duration = 120

        elif any(
            word in category
            for word in [
                "museum",
                "aquarium",
                "gallery",
            ]
        ):
            duration = 150

        elif any(
            word in category
            for word in [
                "food",
                "restaurant",
                "cafe",
                "market",
            ]
        ):
            duration = 90

        elif any(
            word in category
            for word in [
                "shopping",
                "anime",
                "technology",
                "arcade",
            ]
        ):
            duration = 180

        else:
            duration = 120

        enriched.append(
            activity.model_copy(
                update={
                    "estimated_duration_minutes":
                        duration,
                    "duration_estimate_basis": "category_fallback_estimate",
                }
            )
        )

    return intelligence.model_copy(
        update={
            "activities": enriched
        }
    )

# ==================================================
# ROUTING NODE
# ==================================================

def routing_node(
    state: TravelRequestState,
) -> dict:

    intelligence = state[
        "activity_intelligence"
    ]

    enriched, matrix = (
        build_travel_matrix(
            intelligence
        )
    )

    return {
        "activity_intelligence": enriched,
        "travel_matrix": matrix,
    }


def cost_research_node(state: TravelRequestState) -> dict:
    trip = state["final_trip"]
    research = research_trip_costs(trip, state["activity_intelligence"])
    activities = state["activity_intelligence"].activities
    sources_by_url = {source.url: source for source in research.sources}
    free_admissions = {
        re.sub(r"[^a-z0-9]+", "", item.activity_name.casefold()): item
        for item in research.verified_free_activities
    }
    enriched = []
    for activity in activities:
        normalized_activity_name = re.sub(r"[^a-z0-9]+", "", activity.name.casefold())
        price = next((
            estimate for estimate in research.estimates
            if estimate.category == "activities_attractions"
            and estimate.scope == "entity"
            and estimate.entity_name is not None
            and re.sub(r"[^a-z0-9]+", "", estimate.entity_name.casefold()) == normalized_activity_name
            and estimate.currency == trip.currency
            and estimate.basis in {"per_traveler", "per_admission"}
        ), None)
        source = sources_by_url.get(price.source_url) if price else None
        if price:
            enriched.append(activity.model_copy(update={
                "estimated_cost": price.amount,
                "currency": price.currency,
                "cost_status": "indicative",
                "admission_status": "priced",
                "cost_basis": "per_traveler",
                "cost_source_url": price.source_url,
                "cost_source_type": price.source_type,
                "cost_retrieved_on": str(price.retrieved_on) if price.retrieved_on else None,
                "cost_confidence": price.confidence,
                "cost_confidence_level": price.confidence_level,
                "cost_evidence": price.evidence_quote,
            }))
        elif (free := free_admissions.get(normalized_activity_name)) is not None:
            enriched.append(activity.model_copy(update={
                "admission_status": "verified_free",
                "cost_status": "verified_free",
                "cost_source_url": free.source_url,
                "cost_source_type": "official",
                "cost_retrieved_on": str(free.retrieved_on),
                "cost_confidence_level": "high",
                "cost_evidence": free.evidence_quote,
            }))
        else:
            enriched.append(activity)
    intelligence = state["activity_intelligence"].model_copy(update={"activities": enriched})
    return {
        "activity_intelligence": intelligence,
        "cost_research": research,
        # Attraction admissions are attached to individual activities below;
        # treating a single ticket as the whole-trip activities category cost
        # would misstate the category total.
        "budget_cost_estimates": [
            estimate for estimate in research.estimates
            if estimate.category not in {"activities_attractions", "local_transportation", "accommodation"}
        ],
    }


def prepare_budget_allocation_node(
    state: TravelRequestState,
) -> dict:
    trip = state["final_trip"]
    allocation = build_budget_allocation(
        trip=trip,
        cost_estimates=state.get("budget_cost_estimates", []),
    )
    return {
        "budget_allocation": allocation,
        "budget_approved": False,
        "status": "budget_review",
    }


def budget_review_node(
    state: TravelRequestState,
) -> dict:
    allocation: BudgetAllocation = state["budget_allocation"]
    approval = interrupt({
        "type": "budget_review",
        "message": "Review and confirm category caps before generating the itinerary.",
        "budget_allocation": allocation.model_dump(mode="json"),
    })
    if not isinstance(approval, dict):
        raise ValueError("Budget approval must contain category allocations.")
    trip = state["final_trip"]
    research = state.get("cost_research")
    selected_rows = approval.get("cost_option_selections", [])
    if not isinstance(selected_rows, list):
        raise ValueError("Cost option selections must be a list.")
    selected_estimates = resolve_cost_option_selections(
        research.options if research else [], selected_rows, trip,
    )
    selected_categories = {estimate.category for estimate in selected_estimates}
    base_estimates = [
        estimate for estimate in state.get("budget_cost_estimates", [])
        if estimate.category not in selected_categories
    ]
    if selected_estimates:
        allocation = build_budget_allocation(trip, base_estimates + selected_estimates)
    updated = apply_budget_edits(
        allocation,
        approval.get("category_allocations", {}),
    )
    intelligence = state["activity_intelligence"]
    manual_costs = approval.get("activity_costs", {})
    known_names = {activity.name for activity in intelligence.activities}
    if set(manual_costs) - known_names:
        raise ValueError("Manual activity costs contain an unknown activity.")
    edited_activities = []
    for activity in intelligence.activities:
        if activity.name not in manual_costs:
            edited_activities.append(activity)
            continue
        raw = manual_costs[activity.name]
        if isinstance(raw, bool):
            raise ValueError("Manual activity costs must be monetary amounts.")
        try:
            amount = float(raw)
        except (TypeError, ValueError) as error:
            raise ValueError("Manual activity costs must be valid monetary amounts.") from error
        if not isfinite(amount) or amount < 0:
            raise ValueError("Manual activity costs must be finite and non-negative.")
        edited_activities.append(activity.model_copy(update={
            "estimated_cost": round(amount, 2),
            "currency": state["final_trip"].currency,
            "cost_status": "user_provided",
            "admission_status": "priced",
            "cost_basis": "per_traveler",
            "cost_source_url": None,
            "cost_retrieved_on": None,
            "cost_confidence": None,
            "cost_confidence_level": None,
            "cost_evidence": "User-entered estimate",
        }))
    return {
        "budget_allocation": updated,
        "activity_intelligence": intelligence.model_copy(update={"activities": edited_activities}),
        "budget_approved": True,
        "status": "optimizing",
    }

# ==================================================
# ITINERARY OPTIMIZATION NODE
# ==================================================

def optimize_itinerary_node(
    state: TravelRequestState,
) -> dict:

    trip = state["final_trip"]

    intelligence = state[
        "activity_intelligence"
    ]

    matrix = state[
        "travel_matrix"
    ]

    weather = state[
        "weather_context"
    ]
    budget_allocation = state["budget_allocation"]
    if not state.get("budget_approved"):
        raise ValueError("Budget allocation must be confirmed before itinerary optimization.")

    # Number of calendar days in the trip
    number_of_days = (
        trip.return_date
        - trip.departure_date
    ).days + 1

    # Convert weather information into
    # one suitability value per day
    weather_by_day = [
        risk.outdoor_suitability
        for risk in weather.risks
    ]

    # If weather data contains fewer days
    # than the trip, fill the remaining days.
    while len(weather_by_day) < number_of_days:
        weather_by_day.append(
            "unknown"
        )

    weather_by_day = weather_by_day[
        :number_of_days
    ]

    # The return date is reserved for return travel unless the user has
    # supplied a departure time. The request model has no flight-time field,
    # so scheduling a full sightseeing day would imply unavailable details.
    # Reserve one hour on usable sightseeing days for routine schedule variation.
    # This is an explicit planning margin, not a claimed traffic or queue forecast.
    day_buffers = [60] * number_of_days
    available_minutes_by_day = [600 - buffer for buffer in day_buffers]
    day_schedule_notes = [None] * number_of_days
    if number_of_days > 1:
        day_schedule_notes[0] = (
            "Arrival-day sightseeing is provisional because the arrival time was not provided; the schedule is a planning window, not a clock-time guarantee."
        )
        available_minutes_by_day[-1] = 0
        day_buffers[-1] = 0
        day_schedule_notes[-1] = (
            "Return travel day: no local activities scheduled because the return departure time was not provided."
        )

    itinerary = optimize_itinerary(
        activity_intelligence=intelligence,
        travel_matrix=matrix,
        number_of_days=number_of_days,

        # 10 planning hours per day
        daily_minutes=600,
        daily_minutes_by_day=available_minutes_by_day,
        daily_buffer_minutes_by_day=day_buffers,
        day_schedule_notes=day_schedule_notes,

        # Use the category cap approved by the traveler.
        activity_budget=budget_allocation.amount_for("activities_attractions"),
        budget_currency=budget_allocation.currency,
        travelers=trip.travelers,

        weather_suitability_by_day=(
            weather_by_day
        ),
    )

    return {
        "optimized_itinerary": itinerary,
        "status": "complete",
    }


# --------------------------------------------------
# BUILD THE GRAPH
# --------------------------------------------------

builder = StateGraph(
    TravelRequestState
)


builder.add_node(
    "understand_request",
    instrument_workflow_node("understand_request", understand_request_node),
)

builder.add_node(
    "clarify",
    instrument_workflow_node("clarify", clarification_node),
)

builder.add_node(
    "process_followup",
    instrument_workflow_node("process_followup", process_followup_node),
)

builder.add_node(
    "finalize",
    instrument_workflow_node("finalize", finalize_request_node),
)

builder.add_node(
    "research_destination",
    instrument_workflow_node("research_destination", research_destination_node),
)

builder.add_node(
    "weather_intelligence",
    instrument_workflow_node("weather_intelligence", weather_intelligence_node),
)

builder.add_node(
    "context_ready",
    instrument_workflow_node("context_ready", context_ready_node),
)

builder.add_node(
    "activity_intelligence",
    instrument_workflow_node("activity_intelligence", activity_intelligence_node),
)

builder.add_node(
    "routing",
    instrument_workflow_node("routing", routing_node),
)

builder.add_node("cost_research", instrument_workflow_node("cost_research", cost_research_node))

builder.add_node(
    "prepare_budget_allocation",
    instrument_workflow_node("prepare_budget_allocation", prepare_budget_allocation_node),
)

builder.add_node(
    "budget_review",
    instrument_workflow_node("budget_review", budget_review_node),
)

builder.add_node(
    "optimize_itinerary",
    instrument_workflow_node("optimize_itinerary", optimize_itinerary_node),
)

# --------------------------------------------------
# EDGES
# --------------------------------------------------

# START → understand first message
builder.add_edge(
    START,
    "understand_request",
)


# After first understanding:
#
# complete → finalize
# incomplete → clarify
builder.add_conditional_edges(
    "understand_request",
    route_request,
    {
        "clarify": "clarify",
        "finalize": "finalize",
    },
)


# After user answers the interrupt:
#
# clarify → process follow-up
builder.add_edge(
    "clarify",
    "process_followup",
)


# After merging:
#
# still incomplete → clarify AGAIN
# complete → finalize
builder.add_conditional_edges(
    "process_followup",
    route_request,
    {
        "clarify": "clarify",
        "finalize": "finalize",
    },
)


# --------------------------------------------------
# PARALLEL CONTEXT GATHERING
# --------------------------------------------------

# After finalizing the trip,
# start Destination Research.

builder.add_edge(
    "finalize",
    "research_destination",
)


# At the SAME stage,
# also start Weather Intelligence.

builder.add_edge(
    "finalize",
    "weather_intelligence",
)


# Wait until BOTH branches finish.

builder.add_edge(
    [
        "research_destination",
        "weather_intelligence",
    ],
    "context_ready",
)


# Only then finish the graph.

builder.add_edge(
    "context_ready",
    "activity_intelligence",
)

builder.add_edge(
    "activity_intelligence",
    "routing",
)

builder.add_edge("routing", "cost_research")
builder.add_edge("cost_research", "prepare_budget_allocation")
builder.add_edge("prepare_budget_allocation", "budget_review")
builder.add_edge("budget_review", "optimize_itinerary")

builder.add_edge(
    "optimize_itinerary",
    END,
)


# --------------------------------------------------
# CHECKPOINTER
# --------------------------------------------------

_checkpoint_models = [
    ActivityCandidate,
    ActivityIntelligence,
    BudgetAllocation,
    BudgetCategoryAllocation,
    BudgetCostEstimate,
    CostResearchResult,
    CostResearchSource,
    CostPriceStatement,
    CostEvidenceOption,
    VerifiedFreeAdmissionEvidence,
    DestinationRecommendation,
    DestinationResearch,
    DailyWeather,
    OptimizedDay,
    OptimizedItinerary,
    ResearchSource,
    ScheduledActivity,
    TravelMatrix,
    TripRequest,
    TripRequestDraft,
    WeatherContext,
    WeatherRisk,
]

# JsonPlusSerializer uses msgpack without pickle fallback. Explicitly allow
# only the Pydantic models that can appear in graph state, so restoring a
# checkpoint preserves their types without permitting arbitrary module loads.
checkpoint_serializer = JsonPlusSerializer(
    pickle_fallback=False,
    allowed_msgpack_modules=_checkpoint_models,
)
database_pool = initialize_database()
if database_pool is not None:
    from langgraph.checkpoint.postgres import PostgresSaver

    checkpointer = PostgresSaver(database_pool, serde=checkpoint_serializer)
    checkpointer.setup()
else:
    checkpointer = MemorySaver(serde=checkpoint_serializer)


# Compile graph with persistence enabled.
travel_request_graph = builder.compile(
    checkpointer=checkpointer
)
