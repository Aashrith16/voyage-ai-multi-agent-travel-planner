from voyage_ai.models.trip import TripRequest, TripRequestDraft


REQUIRED_TRIP_FIELDS = [
    "origin",
    "destination",
    "departure_date",
    "return_date",
    "travelers",
    "budget",
]


def merge_trip_drafts(
    previous: TripRequestDraft,
    new: TripRequestDraft,
) -> TripRequestDraft:
    """
    Merge previously known trip information with new information.

    New non-empty values replace old values.
    Missing new values do not erase old values.
    Interests from both messages are combined.
    """

    previous_data = previous.model_dump(
        exclude={"missing_fields"}
    )

    new_data = new.model_dump(
        exclude={"missing_fields"}
    )

    merged_data = {}

    for field, previous_value in previous_data.items():
        new_value = new_data.get(field)

        # Interests are combined instead of replaced.
        if field == "interests":
            combined_interests = (
                (previous_value or [])
                + (new_value or [])
            )

            # Remove duplicates while keeping order.
            merged_data[field] = list(
                dict.fromkeys(combined_interests)
            )

        # If the new message contains a value,
        # use the new value.
        elif new_value is not None:
            merged_data[field] = new_value

        # Otherwise preserve what we already knew.
        else:
            merged_data[field] = previous_value

    merged = TripRequestDraft(**merged_data)

    merged.missing_fields = [
        field
        for field in REQUIRED_TRIP_FIELDS
        if getattr(merged, field) is None
    ]

    return merged


def is_trip_request_complete(
    draft: TripRequestDraft,
) -> bool:
    """
    Return True when all required trip fields are available.
    """

    return len(draft.missing_fields) == 0


def finalize_trip_request(
    draft: TripRequestDraft,
) -> TripRequest:
    """
    Convert a complete draft into the strict TripRequest model.
    """

    if not is_trip_request_complete(draft):
        raise ValueError(
            "Trip request cannot be finalized because "
            f"these fields are missing: {draft.missing_fields}"
        )

    return TripRequest(
        origin=draft.origin,
        destination=draft.destination,
        departure_date=draft.departure_date,
        return_date=draft.return_date,
        travelers=draft.travelers,
        budget=draft.budget,
        currency=draft.currency or "INR",
        interests=draft.interests,
    )