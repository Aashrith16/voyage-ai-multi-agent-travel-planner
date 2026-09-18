from voyage_ai.models.activity import (
    ActivityCandidate,
    ActivityIntelligence,
)
from voyage_ai.services.routing_service import (
    build_travel_matrix,
)


activity_intelligence = (
    ActivityIntelligence(
        destination="Tokyo",

        activities=[
            ActivityCandidate(
                name="Akihabara",
                category=(
                    "anime and technology"
                ),
                description=(
                    "Anime, electronics "
                    "and gaming area."
                ),
                environment="mixed",
                preference_score=0.9,
                weather_sensitive=True,
                source_ids=[1],
            ),

            ActivityCandidate(
                name="Ueno Park",
                category="park",
                description=(
                    "Large outdoor park "
                    "in Tokyo."
                ),
                environment="outdoor",
                preference_score=0.7,
                weather_sensitive=True,
                source_ids=[2],
            ),

            ActivityCandidate(
                name="Tokyo Skytree",
                category="observation",
                description=(
                    "Observation tower "
                    "and attraction."
                ),
                environment="indoor",
                preference_score=0.6,
                weather_sensitive=False,
                source_ids=[3],
            ),
        ],
    )
)


enriched, matrix = (
    build_travel_matrix(
        activity_intelligence
    )
)


print(
    "\n======================================"
)

print(
    "ENRICHED ACTIVITIES"
)

print(
    "======================================"
)


for activity in enriched.activities:

    print(
        f"\n{activity.name}"
    )

    print(
        f"Latitude: "
        f"{activity.latitude}"
    )

    print(
        f"Longitude: "
        f"{activity.longitude}"
    )


print(
    "\n======================================"
)

print(
    "TRAVEL TIME MATRIX (MINUTES)"
)

print(
    "======================================"
)


print(
    "Locations:"
)

print(
    matrix.locations
)


for row in matrix.durations_minutes:

    print(row)


print(
    "\n======================================"
)

print(
    "ROAD DISTANCE MATRIX (KM)"
)

print(
    "======================================"
)


for row in matrix.distances_km:

    print(row)