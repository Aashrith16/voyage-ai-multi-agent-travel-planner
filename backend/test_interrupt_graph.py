from langgraph.types import Command

from voyage_ai.graph.workflow import (
    travel_request_graph,
)


# --------------------------------------------------
# UNIQUE ID FOR THIS CONVERSATION
# --------------------------------------------------

config = {
    "configurable": {
        "thread_id": "tokyo-trip-demo-001"
    }
}


# --------------------------------------------------
# MESSAGE 1
# --------------------------------------------------

first_message = """
I want to visit Tokyo.

I like anime and Japanese food.
"""


print("\n======================================")
print("USER MESSAGE 1")
print("======================================")

print(first_message)


# Start the graph.
result = travel_request_graph.invoke(
    {
        "user_input": first_message,
    },
    config=config,
)


# --------------------------------------------------
# GRAPH SHOULD NOW BE PAUSED
# --------------------------------------------------

if "__interrupt__" in result:

    print("\n======================================")
    print("VOYAGEAI PAUSED FOR USER INPUT")
    print("======================================")

    for interruption in result[
        "__interrupt__"
    ]:

        payload = interruption.value

        print("\nMESSAGE:")
        print(payload["message"])

        print("\nQUESTIONS:")

        for question in payload["questions"]:
            print(f"- {question}")


# --------------------------------------------------
# USER MESSAGE 2
# --------------------------------------------------

print("\nPlease answer the questions above.")

second_message = input(
    "\nYour response: "
)


print("\n======================================")
print("USER MESSAGE 2")
print("======================================")

print(second_message)


# --------------------------------------------------
# RESUME THE SAME GRAPH
# --------------------------------------------------

result = travel_request_graph.invoke(
    Command(
        resume=second_message
    ),
    config=config,
)


# --------------------------------------------------
# RESULT
# --------------------------------------------------

print("\n======================================")
print("FINAL GRAPH STATUS")
print("======================================")

print(result["status"])


if result["status"] == "complete":

    print("\n======================================")
    print("FINAL TRIP REQUEST")
    print("======================================")

    print(
        result[
            "final_trip"
        ].model_dump_json(
            indent=2
        )
    )


elif "__interrupt__" in result:

    print("\nMORE INFORMATION IS REQUIRED:")

    for interruption in result[
        "__interrupt__"
    ]:

        for question in (
            interruption.value["questions"]
        ):
            print(f"- {question}")