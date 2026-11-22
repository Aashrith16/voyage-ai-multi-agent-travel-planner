"""Runnable demo; live provider calls require VOYAGEAI_RUN_LIVE_TESTS=1."""
import os


def main() -> None:
    if os.getenv("VOYAGEAI_RUN_LIVE_TESTS") != "1":
        print("Live demo skipped. Set VOYAGEAI_RUN_LIVE_TESTS=1 to enable provider calls.")
        return

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

    print("\nTOTAL RECOMMENDATIONS:")
    print(len(research.recommendations))

    print("\nRECOMMENDATION NAMES:")

    for index, recommendation in enumerate(
        research.recommendations,
        start=1,
    ):
        print(
            f"{index}. {recommendation.name}"
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


if __name__ == "__main__":
    main()
