"""Runnable demo; live provider calls require VOYAGEAI_RUN_LIVE_TESTS=1."""
import os


def main() -> None:
    if os.getenv("VOYAGEAI_RUN_LIVE_TESTS") != "1":
        print("Live demo skipped. Set VOYAGEAI_RUN_LIVE_TESTS=1 to enable provider calls.")
        return

    from voyage_ai.agents.request_agent import (
        understand_trip_request,
        get_clarification_questions,
    )


    user_request = """
    I want to visit Tokyo next month.

    I like anime and Japanese food.
    """


    trip = understand_trip_request(user_request)


    print("\n--- ORIGINAL USER REQUEST ---")
    print(user_request)

    print("\n--- AI EXTRACTED TRAVEL REQUEST ---")
    print(trip)

    print("\n--- STRUCTURED JSON ---")
    print(trip.model_dump_json(indent=2))

    print("\n--- MISSING FIELDS ---")
    print(trip.missing_fields)

    questions = get_clarification_questions(trip)

    print("\n--- QUESTIONS FOR USER ---")

    for question in questions:
        print(f"- {question}")


if __name__ == "__main__":
    main()
