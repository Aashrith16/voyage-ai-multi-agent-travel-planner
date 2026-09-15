from voyage_ai.agents.destination_agent import (
    research_destination,
)
from voyage_ai.models.trip import TripRequest


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


research = research_destination(
    trip
)


print("\n======================================")
print("DESTINATION RESEARCH")
print("======================================")


print("\nDESTINATION:")
print(research.destination)


print("\nSUMMARY:")
print(research.summary)


print("\nRECOMMENDATIONS:")

for recommendation in research.recommendations:

    print(
        f"\n- {recommendation.name}"
    )

    print(
        f"  Category: {recommendation.category}"
    )

    print(
        f"  Why: {recommendation.why_recommended}"
    )

    print(
        f"  Sources: {recommendation.source_ids}"
    )


print("\nPRACTICAL TIPS:")

for tip in research.practical_tips:
    print(f"- {tip}")


print("\nSOURCES:")

for source in research.sources:

    print(
        f"[{source.id}] "
        f"{source.title}"
    )

    print(source.url)


print("\n======================================")