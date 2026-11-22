"""Runnable demo; live provider calls require VOYAGEAI_RUN_LIVE_TESTS=1."""
import os


def main() -> None:
    if os.getenv("VOYAGEAI_RUN_LIVE_TESTS") != "1":
        print("Live demo skipped. Set VOYAGEAI_RUN_LIVE_TESTS=1 to enable provider calls.")
        return

    from voyage_ai.graph.workflow import (
        travel_request_graph,
    )


    # --------------------------------------------------
    # TEST 1: INCOMPLETE REQUEST
    # --------------------------------------------------

    user_request = """
    I want to visit Tokyo.

    I like anime and Japanese food.
    """


    result = travel_request_graph.invoke(
        {
            "user_input": user_request,
        }
    )


    print("\n======================================")
    print("GRAPH RESULT")
    print("======================================")

    print("\nSTATUS:")
    print(result["status"])


    print("\nEXTRACTED DRAFT:")
    print(
        result["draft"].model_dump_json(
            indent=2
        )
    )


    if result["status"] == "needs_clarification":

        print("\nQUESTIONS:")

        for question in result[
            "clarification_questions"
        ]:
            print(f"- {question}")


    if result["status"] == "complete":

        print("\nFINAL TRIP:")

        print(
            result["final_trip"].model_dump_json(
                indent=2
            )
        )


if __name__ == "__main__":
    main()
