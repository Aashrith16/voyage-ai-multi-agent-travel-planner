from voyage_ai.agents.request_agent import (
    get_clarification_questions,
    understand_trip_request,
)

from voyage_ai.services.trip_request_service import (
    finalize_trip_request,
    is_trip_request_complete,
    merge_trip_drafts,
)


# --------------------------------------------------
# USER MESSAGE 1
# --------------------------------------------------

first_message = """
I want to visit Tokyo.

I like anime and Japanese food.
"""


print("\n======================================")
print("USER MESSAGE 1")
print("======================================")
print(first_message)


# Gemini understands the first message.
first_draft = understand_trip_request(first_message)


print("\n--- FIRST DRAFT ---")
print(first_draft.model_dump_json(indent=2))


# Find what information is still missing.
questions = get_clarification_questions(first_draft)


print("\n--- VOYAGEAI QUESTIONS ---")

for question in questions:
    print(f"- {question}")


# --------------------------------------------------
# USER MESSAGE 2
# --------------------------------------------------

second_message = """
I am traveling from Hyderabad.

My trip is from 10 December 2026
to 16 December 2026.

There are 2 travelers.

My total budget is 200000 rupees.
"""


print("\n======================================")
print("USER MESSAGE 2")
print("======================================")
print(second_message)


# Gemini understands only the NEW message.
second_draft = understand_trip_request(second_message)


print("\n--- SECOND DRAFT ---")
print(second_draft.model_dump_json(indent=2))


# --------------------------------------------------
# MERGE OLD STATE + NEW INFORMATION
# --------------------------------------------------

merged_draft = merge_trip_drafts(
    first_draft,
    second_draft,
)


print("\n======================================")
print("MERGED TRAVEL REQUEST")
print("======================================")

print(
    merged_draft.model_dump_json(
        indent=2
    )
)


print("\n--- MISSING FIELDS ---")
print(merged_draft.missing_fields)


print("\n--- IS REQUEST COMPLETE? ---")

complete = is_trip_request_complete(
    merged_draft
)

print(complete)


# --------------------------------------------------
# CREATE FINAL STRICT TRIP REQUEST
# --------------------------------------------------

if complete:

    final_trip = finalize_trip_request(
        merged_draft
    )

    print("\n======================================")
    print("FINAL TRIP REQUEST")
    print("======================================")

    print(
        final_trip.model_dump_json(
            indent=2
        )
    )

else:

    remaining_questions = (
        get_clarification_questions(
            merged_draft
        )
    )

    print("\n--- MORE INFORMATION NEEDED ---")

    for question in remaining_questions:
        print(f"- {question}")