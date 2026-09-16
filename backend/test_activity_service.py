from voyage_ai.models.destination import (
    DestinationRecommendation,
    DestinationResearch,
)
from voyage_ai.models.trip import TripRequest
from voyage_ai.services.activity_service import (
    build_activity_intelligence,
)


# --------------------------------------------------
# TEST TRIP
# --------------------------------------------------

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


# --------------------------------------------------
# MOCK DESTINATION RESEARCH
#
# We use mock data here because we are testing
# Activity Intelligence only.
#
# No Gemini call.
# No Tavily call.
# No API cost.
# --------------------------------------------------

research = DestinationResearch(
    destination="Tokyo",

    summary=(
        "Test destination research for Tokyo."
    ),

    recommendations=[
        DestinationRecommendation(
            name="Akihabara",

            category=(
                "anime and technology"
            ),

            why_recommended=(
                "Popular for anime stores, "
                "electronics, gaming and arcades."
            ),

            source_ids=[1],
        ),

        DestinationRecommendation(
            name="Ueno Park",

            category="park",

            why_recommended=(
                "Large outdoor park suitable "
                "for walking and sightseeing."
            ),

            source_ids=[2],
        ),

        DestinationRecommendation(
            name="Tokyo Food Market",

            category="food market",

            why_recommended=(
                "Indoor food destination featuring "
                "Japanese cuisine and local dishes."
            ),

            source_ids=[3],
        ),
    ],

    practical_tips=[],

    # Sources are not needed for this unit test.
    sources=[],
)


# --------------------------------------------------
# BUILD ACTIVITY INTELLIGENCE
# --------------------------------------------------

activity_intelligence = (
    build_activity_intelligence(
        trip=trip,
        research=research,
    )
)


# --------------------------------------------------
# PRINT RESULT
# --------------------------------------------------

print(
    "\n======================================"
)

print(
    "VOYAGEAI ACTIVITY INTELLIGENCE"
)

print(
    "======================================"
)


print(
    activity_intelligence.model_dump_json(
        indent=2
    )
)