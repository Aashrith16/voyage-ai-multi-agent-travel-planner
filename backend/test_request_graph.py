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