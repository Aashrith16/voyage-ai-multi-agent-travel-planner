from math import (
    asin,
    cos,
    radians,
    sin,
    sqrt,
)

from voyage_ai.models.activity import (
    ActivityCandidate,
    ActivityIntelligence,
)
from voyage_ai.tools.place_search import (
    resolve_place,
)


def enrich_activity_location(
    activity: ActivityCandidate,
    destination: str,
) -> ActivityCandidate:
    """
    Resolve one activity to a real place and
    attach latitude and longitude.

    We use model_copy so the original object
    is not modified directly.
    """

    try:
        place = resolve_place(
            place_name=activity.name,
            destination=destination,
        )

        return activity.model_copy(
            update={
                "latitude": place.latitude,
                "longitude": place.longitude,
            }
        )

    except Exception as error:
        print(
            f"Could not resolve "
            f"{activity.name}: {error}"
        )

        return activity


def enrich_activity_intelligence(
    intelligence: ActivityIntelligence,
) -> ActivityIntelligence:
    """
    Add real coordinates to every activity.
    """

    enriched_activities = []

    for activity in intelligence.activities:

        enriched = enrich_activity_location(
            activity=activity,
            destination=(
                intelligence.destination
            ),
        )

        enriched_activities.append(
            enriched
        )

    return intelligence.model_copy(
        update={
            "activities":
                enriched_activities
        }
    )


def calculate_distance_km(
    latitude_1: float,
    longitude_1: float,
    latitude_2: float,
    longitude_2: float,
) -> float:
    """
    Calculate straight-line distance between
    two geographic coordinates.

    Uses the Haversine formula.
    """

    earth_radius_km = 6371.0

    lat1 = radians(
        latitude_1
    )

    lon1 = radians(
        longitude_1
    )

    lat2 = radians(
        latitude_2
    )

    lon2 = radians(
        longitude_2
    )


    delta_lat = (
        lat2 - lat1
    )

    delta_lon = (
        lon2 - lon1
    )


    value = (
        sin(delta_lat / 2) ** 2
        +
        cos(lat1)
        * cos(lat2)
        * sin(delta_lon / 2) ** 2
    )


    central_angle = (
        2
        * asin(
            sqrt(value)
        )
    )


    distance = (
        earth_radius_km
        * central_angle
    )


    return round(
        distance,
        2,
    )