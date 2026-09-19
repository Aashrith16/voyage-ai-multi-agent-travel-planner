from voyage_ai.models.trip import TripRequest

from voyage_ai.services.geospatial_service import (
    enrich_activity_intelligence,
)

from voyage_ai.agents.destination_agent import (
    research_destination,
)

from voyage_ai.services.activity_service import (
    build_activity_intelligence,
)


trip = TripRequest(
    origin="Hyderabad",
    destination="Tokyo",
    departure_date="2026-12-10",
    return_date="2026-12-16",
    travelers=2,
    budget=200000,
    currency="INR",
    interests=[
        "anime",
        "technology",
        "Japanese food",
    ],
)


print(
    "\n======================================"
)

print(
    "STEP 1: DESTINATION RESEARCH"
)

print(
    "======================================"
)


research = research_destination(
    trip
)


print(
    "\nTOTAL DESTINATION RECOMMENDATIONS:"
)

print(
    len(research.recommendations)
)


print(
    "\nDESTINATION RECOMMENDATIONS:"
)


for index, recommendation in enumerate(
    research.recommendations,
    start=1,
):
    print(
        f"{index}. {recommendation.name}"
    )


print(
    "\n======================================"
)

print(
    "STEP 2: ACTIVITY INTELLIGENCE"
)

print(
    "======================================"
)


activity_intelligence = (
    build_activity_intelligence(
        trip=trip,
        research=research,
    )
)


print(
    "\nTOTAL ACTIVITY CANDIDATES:"
)

print(
    len(
        activity_intelligence.activities
    )
)


print(
    "\nACTIVITY CANDIDATES:"
)

print(
    "\n======================================"
)

print(
    "STEP 3: GEOSPATIAL RESOLUTION"
)

print(
    "======================================"
)


enriched_intelligence = (
    enrich_activity_intelligence(
        intelligence=activity_intelligence,
    )
)


resolved = [
    activity
    for activity in enriched_intelligence.activities
    if (
        activity.latitude is not None
        and activity.longitude is not None
    )
]


unresolved = [
    activity
    for activity in enriched_intelligence.activities
    if (
        activity.latitude is None
        or activity.longitude is None
    )
]


print(
    "\nTOTAL RESOLVED:"
)

print(
    len(resolved)
)


print(
    "\nTOTAL UNRESOLVED:"
)

print(
    len(unresolved)
)


print(
    "\nRESOLVED PLACES:"
)

for index, activity in enumerate(
    resolved,
    start=1,
):
    print(
        f"{index}. {activity.name}"
        f" -> "
        f"{activity.latitude}, "
        f"{activity.longitude}"
    )


print(
    "\nUNRESOLVED PLACES:"
)

if not unresolved:
    print("None")
else:
    for index, activity in enumerate(
        unresolved,
        start=1,
    ):
        print(
            f"{index}. {activity.name}"
        )

for index, activity in enumerate(
    activity_intelligence.activities,
    start=1,
):
    print(
        f"{index}. {activity.name}"
        f" | preference={activity.preference_score}"
        f" | environment={activity.environment}"
    )


print(
    "\n======================================"
)

print(
    "PIPELINE SUMMARY"
)

print(
    "======================================"
)


print(
    "Destination recommendations:",
    len(research.recommendations),
)

print(
    "Activity candidates:",
    len(
        activity_intelligence.activities
    ),
)

print(
    "Resolved places:",
    len(resolved),
)

print(
    "Unresolved places:",
    len(unresolved),
)

resolution_rate = (
    len(resolved)
    / len(enriched_intelligence.activities)
    * 100
    if enriched_intelligence.activities
    else 0
)

print(
    "Resolution rate:",
    f"{resolution_rate:.1f}%",
)

print("\nUNRESOLVED PLACE NAMES:")

if unresolved:
    for index, activity in enumerate(
        unresolved,
        start=1,
    ):
        print(
            f"{index}. {activity.name}"
        )
else:
    print("None")