from voyage_ai.models.activity import (
    ActivityCandidate,
    ActivityIntelligence,
)
from voyage_ai.services.routing_service import (
    build_travel_matrix,
)
from voyage_ai.services.itinerary_optimizer import (
    optimize_itinerary,
)


activities = ActivityIntelligence(
    destination="Tokyo",

    activities=[
        ActivityCandidate(
            name="Akihabara",

            category="anime and technology",

            description=(
                "Anime, electronics and gaming."
            ),

            environment="mixed",

            estimated_duration_minutes=180,

            estimated_cost=3000,

            currency="INR",

            preference_score=0.95,

            weather_sensitive=True,

            source_ids=[1],

            confidence=0.9,
        ),


        ActivityCandidate(
            name="Ueno Park",

            category="park",

            description=(
                "Large outdoor park."
            ),

            environment="outdoor",

            estimated_duration_minutes=120,

            estimated_cost=0,

            currency="INR",

            preference_score=0.65,

            weather_sensitive=True,

            source_ids=[2],

            confidence=0.9,
        ),


        ActivityCandidate(
            name="Tokyo Skytree",

            category="observation",

            description=(
                "Observation tower."
            ),

            environment="indoor",

            estimated_duration_minutes=120,

            estimated_cost=2500,

            currency="INR",

            preference_score=0.75,

            weather_sensitive=False,

            source_ids=[3],

            confidence=0.9,
        ),
    ],
)


print(
    "\n======================================"
)

print(
    "BUILDING TRAVEL MATRIX"
)

print(
    "======================================"
)


enriched, matrix = (
    build_travel_matrix(
        activities
    )
)


print(
    "\n======================================"
)

print(
    "RUNNING OR-TOOLS OPTIMIZER"
)

print(
    "======================================"
)


itinerary = optimize_itinerary(
    activity_intelligence=enriched,

    travel_matrix=matrix,

    number_of_days=2,

    # 3 hours available each day
    daily_minutes=180,
)


print(
    "\n======================================"
)

print(
    "OPTIMIZED ITINERARY"
)

print(
    "======================================"
)


for day in itinerary.days:

    print(
        f"\nDAY {day.day_number}"
    )

    print(
        f"Activity time: "
        f"{day.total_activity_minutes} min"
    )

    print(
        f"Travel time: "
        f"{day.total_travel_minutes} min"
    )


    for activity in day.activities:

        print(
            f"\n  {activity.sequence}. "
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
    "\nSELECTED:"
)

print(
    itinerary.selected_activities
)


print(
    "\nDROPPED:"
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