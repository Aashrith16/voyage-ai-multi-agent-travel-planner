"""Runnable demo; live provider calls require VOYAGEAI_RUN_LIVE_TESTS=1."""
import os


def main() -> None:
    if os.getenv("VOYAGEAI_RUN_LIVE_TESTS") != "1":
        print("Live demo skipped. Set VOYAGEAI_RUN_LIVE_TESTS=1 to enable provider calls.")
        return

    from voyage_ai.graph.workflow import (
        travel_request_graph,
    )


    user_request = """
    Plan a trip from Hyderabad to Tokyo
    from 10 December 2026 to 16 December 2026
    for 2 people.

    My total budget is 200000 rupees.

    I like anime, technology, and Japanese food.
    """


    config = {
        "configurable": {
            "thread_id": "parallel-context-test-001"
        }
    }


    result = travel_request_graph.invoke(
        {
            "user_input": user_request,
        },
        config=config,
    )


    print("\n======================================")
    print("WORKFLOW STATUS")
    print("======================================")

    print(result["status"])


    print("\n======================================")
    print("FINAL TRIP")
    print("======================================")

    print(
        result["final_trip"].model_dump_json(
            indent=2
        )
    )


    print("\n======================================")
    print("DESTINATION RESEARCH")
    print("======================================")

    research = result["destination_research"]

    print(research.summary)


    print("\nRECOMMENDATIONS:")

    for recommendation in research.recommendations:

        print(
            f"\n- {recommendation.name}"
        )

        print(
            f"  Category: "
            f"{recommendation.category}"
        )

        print(
            f"  Sources: "
            f"{recommendation.source_ids}"
        )


    print("\n======================================")
    print("WEATHER INTELLIGENCE")
    print("======================================")

    weather = result["weather_context"]


    print(
        f"\nMode: {weather.data_mode}"
    )

    print(
        f"\nDisclaimer:\n"
        f"{weather.disclaimer}"
    )


    print("\nDAILY RISKS:")

    for risk in weather.risks:

        print(f"\n{risk.date}")

        print(
            f"Rain: {risk.rain_risk}"
        )

        print(
            f"Temperature: "
            f"{risk.temperature_risk}"
        )

        print(
            f"Outdoor suitability: "
            f"{risk.outdoor_suitability}"
        )


if __name__ == "__main__":
    main()
