from voyage_ai.models.trip import TripRequestDraft

from voyage_ai.services.trip_request_service import (
    finalize_trip_request,
    is_trip_request_complete,
    merge_trip_drafts,
)


# Information from the user's first message.
first_draft = TripRequestDraft(
    destination="Tokyo",
    interests=[
        "anime",
        "Japanese food",
    ],
)


# Information supplied later by the user.
second_draft = TripRequestDraft(
    origin="Hyderabad",
    departure_date="2026-12-10",
    return_date="2026-12-16",
    travelers=2,
    budget=200000,
)


merged = merge_trip_drafts(
    first_draft,
    second_draft,
)


print("\n--- FIRST DRAFT ---")
print(first_draft.model_dump_json(indent=2))


print("\n--- SECOND DRAFT ---")
print(second_draft.model_dump_json(indent=2))


print("\n--- MERGED DRAFT ---")
print(merged.model_dump_json(indent=2))


print("\n--- MISSING FIELDS ---")
print(merged.missing_fields)


print("\n--- COMPLETE? ---")
print(is_trip_request_complete(merged))


if is_trip_request_complete(merged):
    final_trip = finalize_trip_request(merged)

    print("\n--- FINAL TRIP REQUEST ---")
    print(final_trip.model_dump_json(indent=2))