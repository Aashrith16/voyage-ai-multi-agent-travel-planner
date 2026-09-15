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


result = travel_request_graph.invoke(
    {
        "user_input": user_request,
    },
    config={
        "configurable": {
            "thread_id": "destination-test-001"
        }
    },
)


print("\n======================================")
print("WORKFLOW STATUS")
print("======================================")

print(result["status"])


if "final_trip" in result:

    print("\n======================================")
    print("FINAL TRIP")
    print("======================================")

    print(
        result["final_trip"].model_dump_json(
            indent=2
        )
    )


if "destination_research" in result:

    research = result[
        "destination_research"
    ]

    print("\n======================================")
    print("DESTINATION RESEARCH")
    print("======================================")

    print("\nSUMMARY:")
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
            f"  Why: "
            f"{recommendation.why_recommended}"
        )

        print(
            f"  Source IDs: "
            f"{recommendation.source_ids}"
        )

    print("\nSOURCES:")

    for source in research.sources:

        print(
            f"[{source.id}] "
            f"{source.title}"
        )

        print(source.url)