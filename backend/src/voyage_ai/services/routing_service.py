from voyage_ai.models.activity import (
    ActivityIntelligence,
)
from voyage_ai.models.routing import (
    TravelMatrix,
)
from voyage_ai.services.geospatial_service import (
    calculate_distance_km,
    enrich_activity_intelligence,
)
from voyage_ai.tools.routing import (
    get_route_matrix,
)


def build_fallback_matrix(
    activity_intelligence: ActivityIntelligence,
) -> TravelMatrix:
    """
    Build a distance-only fallback matrix using
    the Haversine formula.

    Travel durations are left as None because
    straight-line distance cannot reliably tell us
    real travel time.
    """

    activities = activity_intelligence.activities

    locations = [
        activity.name
        for activity in activities
    ]

    size = len(activities)

    durations = [
        [None for _ in range(size)]
        for _ in range(size)
    ]

    distances = [
        [None for _ in range(size)]
        for _ in range(size)
    ]


    for i in range(size):

        durations[i][i] = 0.0
        distances[i][i] = 0.0

        for j in range(size):

            if i == j:
                continue

            first = activities[i]
            second = activities[j]

            if (
                first.latitude is None
                or first.longitude is None
                or second.latitude is None
                or second.longitude is None
            ):
                continue

            distances[i][j] = (
                calculate_distance_km(
                    latitude_1=first.latitude,
                    longitude_1=first.longitude,
                    latitude_2=second.latitude,
                    longitude_2=second.longitude,
                )
            )


    return TravelMatrix(
        locations=locations,
        durations_minutes=durations,
        distances_km=distances,
    )


def build_travel_matrix(
    activity_intelligence: ActivityIntelligence,
) -> tuple[
    ActivityIntelligence,
    TravelMatrix,
]:
    """
    Resolve activity coordinates and obtain
    pairwise road-routing information.

    Returns:

        enriched activities
        +
        TravelMatrix
    """

    enriched = (
        enrich_activity_intelligence(
            activity_intelligence
        )
    )


    valid_activities = [
        activity
        for activity in enriched.activities
        if (
            activity.latitude is not None
            and activity.longitude is not None
        )
    ]


    if len(valid_activities) < 2:
        raise ValueError(
            "At least two resolved activities "
            "are required to build a route matrix."
        )


    coordinates = [
        (
            activity.latitude,
            activity.longitude,
        )
        for activity in valid_activities
    ]


    location_names = [
        activity.name
        for activity in valid_activities
    ]


    try:

        raw = get_route_matrix(
            coordinates
        )


        raw_durations = raw[
            "durations"
        ]

        raw_distances = raw[
            "distances"
        ]


        durations_minutes = []

        for row in raw_durations:

            converted_row = []

            for value in row:

                if value is None:
                    converted_row.append(
                        None
                    )

                else:
                    converted_row.append(
                        round(
                            value / 60,
                            1,
                        )
                    )

            durations_minutes.append(
                converted_row
            )


        distances_km = []

        for row in raw_distances:

            converted_row = []

            for value in row:

                if value is None:
                    converted_row.append(
                        None
                    )

                else:
                    converted_row.append(
                        round(
                            value / 1000,
                            2,
                        )
                    )

            distances_km.append(
                converted_row
            )


        matrix = TravelMatrix(
            locations=location_names,

            durations_minutes=(
                durations_minutes
            ),

            distances_km=(
                distances_km
            ),
        )


        return enriched, matrix


    except Exception as error:

        print(
            "\nOSRM routing failed."
        )

        print(
            f"Reason: {error}"
        )

        print(
            "Using Haversine distance fallback."
        )


        fallback_intelligence = (
            ActivityIntelligence(
                destination=(
                    enriched.destination
                ),

                activities=(
                    valid_activities
                ),
            )
        )


        matrix = build_fallback_matrix(
            fallback_intelligence
        )


        return (
            fallback_intelligence,
            matrix,
        )