from voyage_ai.models.activity import (
    ActivityCandidate,
    ActivityIntelligence,
)
from voyage_ai.services.geospatial_service import (
    calculate_distance_km,
    enrich_activity_intelligence,
)


activities = ActivityIntelligence(
    destination="Tokyo",

    activities=[
        ActivityCandidate(
            name="Akihabara",
            category="anime and technology",
            description=(
                "Anime, electronics and gaming area."
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
                "Large outdoor park in Tokyo."
            ),
            environment="outdoor",
            preference_score=0.6,
            weather_sensitive=True,
            source_ids=[2],
        ),

        ActivityCandidate(
            name="Tokyo Skytree",
            category="observation",
            description=(
                "Observation tower and attraction."
            ),
            environment="indoor",
            preference_score=0.5,
            weather_sensitive=False,
            source_ids=[3],
        ),
    ],
)


print(
    "\n======================================"
)

print(
    "RESOLVING REAL PLACES"
)

print(
    "======================================"
)


enriched = enrich_activity_intelligence(
    activities
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
    "DISTANCES"
)

print(
    "======================================"
)


valid_activities = [
    activity
    for activity in enriched.activities
    if (
        activity.latitude is not None
        and activity.longitude is not None
    )
]


for index in range(
    len(valid_activities) - 1
):

    first = valid_activities[
        index
    ]

    second = valid_activities[
        index + 1
    ]


    distance = calculate_distance_km(
        latitude_1=first.latitude,
        longitude_1=first.longitude,

        latitude_2=second.latitude,
        longitude_2=second.longitude,
    )


    print(
        f"\n{first.name}"
        f" -> "
        f"{second.name}"
    )

    print(
        f"Straight-line distance: "
        f"{distance} km"
    )