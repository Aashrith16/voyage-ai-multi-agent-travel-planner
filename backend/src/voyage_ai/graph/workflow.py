from typing import Literal

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from voyage_ai.agents.destination_agent import research_destination

from voyage_ai.services.weather_service import (
    get_weather_context,
)

from voyage_ai.agents.request_agent import (
    get_clarification_questions,
    understand_trip_request,
)
from voyage_ai.graph.state import TravelRequestState
from voyage_ai.services.trip_request_service import (
    finalize_trip_request,
    is_trip_request_complete,
    merge_trip_drafts,
)


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
    ]

    # Gemini understands only the new reply.
    new_draft = understand_trip_request(
        followup_input
    )

    # Python combines old + new information.
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

    weather_context = get_weather_context(
        destination=final_trip.destination,
        start_date=final_trip.departure_date,
        end_date=final_trip.return_date,
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
    understand_request_node,
)

builder.add_node(
    "clarify",
    clarification_node,
)

builder.add_node(
    "process_followup",
    process_followup_node,
)

builder.add_node(
    "finalize",
    finalize_request_node,
)

builder.add_node(
    "research_destination",
    research_destination_node,
)

builder.add_node(
    "weather_intelligence",
    weather_intelligence_node,
)

builder.add_node(
    "context_ready",
    context_ready_node,
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
    END,
)


# --------------------------------------------------
# CHECKPOINTER
# --------------------------------------------------

memory = MemorySaver()


# Compile graph with persistence enabled.
travel_request_graph = builder.compile(
    checkpointer=memory
)