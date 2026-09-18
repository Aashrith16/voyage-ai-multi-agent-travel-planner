from voyage_ai.models.activity import (
    ActivityCandidate,
    ActivityIntelligence,
)
from voyage_ai.services.itinerary_optimizer import (
    optimize_itinerary,
)
from voyage_ai.services.routing_service import (
    build_travel_matrix,
)


activities = ActivityIntelligence(
    destination="Tokyo",

    activities=[
        ActivityCandidate(
            name="Akihabara",
            category="anime and technology",
            description="Anime, electronics and gaming.",
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
            description="Large outdoor park.",
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
            description="Observation tower.",
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


print("\nBUILDING TRAVEL MATRIX...")


enriched, matrix = build_travel_matrix(
    activities
)


print("\nRUNNING BUDGET + WEATHER OPTIMIZER...")


itinerary = optimize_itinerary(
    activity_intelligence=enriched,
    travel_matrix=matrix,

    number_of_days=2,

    daily_minutes=200,

    activity_budget=4000,

    weather_suitability_by_day=[
        "poor",
        "good",
    ],
)


print("\n======================================")
print("OPTIMIZED ITINERARY")
print("======================================")


for day in itinerary.days:

    print(
        f"\nDAY {day.day_number}"
    )

    print(
        f"Weather: {day.weather_suitability}"
    )

    print(
        f"Activity cost: ₹{day.total_activity_cost}"
    )

    for activity in day.activities:

        print(
            f"  {activity.sequence}. "
            f"{activity.name}"
        )


print("\nSELECTED:")
print(itinerary.selected_activities)

print("\nDROPPED:")
print(itinerary.dropped_activities)

print("\nTOTAL ACTIVITY COST:")
print(
    f"₹{itinerary.total_activity_cost}"
)

print("\nACTIVITY BUDGET:")
print(
    f"₹{itinerary.activity_budget}"
)

print("\nOBJECTIVE VALUE:")
print(itinerary.objective_value)