from voyage_ai.graph.workflow import (
    travel_request_graph,
)


# ==================================================
# COMPLETE USER REQUEST
# ==================================================

user_request = """
Plan a trip from Hyderabad to Tokyo
from 10 December 2026 to 16 December 2026
for 2 people.

My total trip budget is 200000 rupees.

I am interested in anime,
technology and Japanese food.
"""


# ==================================================
# LANGGRAPH THREAD
# ==================================================

config = {
    "configurable": {
        "thread_id":
            "full-voyage-workflow-test-001"
    }
}


print(
    "\n======================================"
)

print(
    "VOYAGEAI FULL WORKFLOW"
)

print(
    "======================================"
)


print(
    "\nUSER REQUEST:"
)

print(
    user_request
)


print(
    "\nStarting VoyageAI..."
)


# ==================================================
# RUN COMPLETE LANGGRAPH
# ==================================================

result = travel_request_graph.invoke(
    {
        "user_input": user_request,
    },
    config=config,
)


# ==================================================
# WORKFLOW STATUS
# ==================================================

print(
    "\n======================================"
)

print(
    "WORKFLOW STATUS"
)

print(
    "======================================"
)

print(
    result.get(
        "status"
    )
)


# ==================================================
# FINAL TRIP REQUEST
# ==================================================

print(
    "\n======================================"
)

print(
    "FINAL TRIP REQUEST"
)

print(
    "======================================"
)


final_trip = result.get(
    "final_trip"
)


if final_trip:

    print(
        final_trip.model_dump_json(
            indent=2
        )
    )


# ==================================================
# DESTINATION RESEARCH
# ==================================================

print(
    "\n======================================"
)

print(
    "DESTINATION RESEARCH"
)

print(
    "======================================"
)


research = result.get(
    "destination_research"
)


if research:

    print(
        f"\nSummary:\n"
        f"{research.summary}"
    )


    print(
        "\nRecommendations:"
    )


    for recommendation in (
        research.recommendations
    ):

        print(
            f"\n- "
            f"{recommendation.name}"
        )

        print(
            f"  Category: "
            f"{recommendation.category}"
        )

        print(
            f"  Why: "
            f"{recommendation.why_recommended}"
        )

        print(
            f"  Sources: "
            f"{recommendation.source_ids}"
        )


# ==================================================
# WEATHER INTELLIGENCE
# ==================================================

print(
    "\n======================================"
)

print(
    "WEATHER INTELLIGENCE"
)

print(
    "======================================"
)


weather = result.get(
    "weather_context"
)


if weather:

    print(
        f"\nData mode: "
        f"{weather.data_mode}"
    )


    print(
        f"\nDisclaimer:\n"
        f"{weather.disclaimer}"
    )


    print(
        "\nDaily weather risks:"
    )


    for risk in weather.risks:

        print(
            f"\n{risk.date}"
        )

        print(
            f"  Rain: "
            f"{risk.rain_risk}"
        )

        print(
            f"  Temperature: "
            f"{risk.temperature_risk}"
        )

        print(
            f"  Outdoor suitability: "
            f"{risk.outdoor_suitability}"
        )


# ==================================================
# ACTIVITY INTELLIGENCE
# ==================================================

print(
    "\n======================================"
)

print(
    "ACTIVITY INTELLIGENCE"
)

print(
    "======================================"
)


activity_intelligence = result.get(
    "activity_intelligence"
)


if activity_intelligence:

    for activity in (
        activity_intelligence.activities
    ):

        print(
            f"\n- {activity.name}"
        )

        print(
            f"  Category: "
            f"{activity.category}"
        )

        print(
            f"  Environment: "
            f"{activity.environment}"
        )

        print(
            f"  Preference score: "
            f"{activity.preference_score}"
        )

        print(
            f"  Planning duration: "
            f"{activity.estimated_duration_minutes} "
            f"minutes"
        )

        print(
            f"  Latitude: "
            f"{activity.latitude}"
        )

        print(
            f"  Longitude: "
            f"{activity.longitude}"
        )


# ==================================================
# TRAVEL MATRIX
# ==================================================

print(
    "\n======================================"
)

print(
    "TRAVEL MATRIX"
)

print(
    "======================================"
)


matrix = result.get(
    "travel_matrix"
)


if matrix:

    print(
        "\nLocations:"
    )

    print(
        matrix.locations
    )


    print(
        "\nTravel times (minutes):"
    )


    for row in (
        matrix.durations_minutes
    ):

        print(
            row
        )


    print(
        "\nRoad distances (km):"
    )


    for row in (
        matrix.distances_km
    ):

        print(
            row
        )


# ==================================================
# OPTIMIZED ITINERARY
# ==================================================

print(
    "\n======================================"
)

print(
    "OPTIMIZED ITINERARY"
)

print(
    "======================================"
)


itinerary = result.get(
    "optimized_itinerary"
)


if itinerary:

    for day in itinerary.days:

        print(
            f"\nDAY {day.day_number}"
        )

        print(
            f"Weather suitability: "
            f"{day.weather_suitability}"
        )

        print(
            f"Activity time: "
            f"{day.total_activity_minutes} min"
        )

        print(
            f"Travel time: "
            f"{day.total_travel_minutes} min"
        )

        print(
            f"Activity cost: "
            f"{day.total_activity_cost}"
        )


        if not day.activities:

            print(
                "  No activity scheduled."
            )


        for activity in day.activities:

            print(
                f"\n  "
                f"{activity.sequence}. "
                f"{activity.name}"
            )

            print(
                f"     Duration: "
                f"{activity.estimated_duration_minutes} min"
            )

            print(
                f"     Travel from previous: "
                f"{activity.travel_from_previous_minutes} min"
            )

            print(
                f"     Preference: "
                f"{activity.preference_score}"
            )


    print(
        "\nSELECTED ACTIVITIES:"
    )

    print(
        itinerary.selected_activities
    )


    print(
        "\nDROPPED ACTIVITIES:"
    )

    print(
        itinerary.dropped_activities
    )


    print(
        "\nOBJECTIVE VALUE:"
    )

    print(
        itinerary.objective_value
    )


print(
    "\n======================================"
)

print(
    "VOYAGEAI WORKFLOW FINISHED"
)

print(
    "======================================"
)