import re

from voyage_ai.models.activity import (
    ActivityCandidate,
    ActivityIntelligence,
)
from voyage_ai.models.destination import (
    DestinationResearch,
)
from voyage_ai.models.trip import TripRequest


def tokenize(text: str) -> set[str]:
    """
    Convert text into lowercase words.

    Example:
    "Japanese Food & Anime"
    becomes:
    {"japanese", "food", "anime"}
    """

    return set(
        re.findall(
            r"[a-zA-Z0-9]+",
            text.lower(),
        )
    )


def calculate_preference_score(
    name: str,
    category: str,
    description: str,
    interests: list[str],
) -> float:
    """
    Calculate how well an activity matches
    the user's interests.

    This is deterministic Python logic.
    """

    activity_text = (
        f"{name} {category} {description}"
    )

    activity_words = tokenize(
        activity_text
    )

    if not interests:
        return 0.5

    matched_interests = 0

    for interest in interests:

        interest_words = tokenize(
            interest
        )

        if (
            interest_words
            and activity_words.intersection(
                interest_words
            )
        ):
            matched_interests += 1

    match_ratio = (
        matched_interests
        / len(interests)
    )

    score = (
        0.4
        + (0.6 * match_ratio)
    )

    return round(
        min(score, 1.0),
        2,
    )


def classify_environment(
    name: str,
    category: str,
    description: str,
) -> str:
    """
    Classify an activity as indoor,
    outdoor, mixed, or unknown.
    """

    text = (
        f"{name} {category} {description}"
    ).lower()

    indoor_keywords = {
        "museum",
        "mall",
        "shopping",
        "arcade",
        "aquarium",
        "restaurant",
        "cafe",
        "gallery",
        "indoor",
        "market",
        "store",
    }

    outdoor_keywords = {
        "park",
        "garden",
        "hiking",
        "beach",
        "outdoor",
        "trail",
        "nature",
        "walking",
    }

    indoor_match = any(
        keyword in text
        for keyword in indoor_keywords
    )

    outdoor_match = any(
        keyword in text
        for keyword in outdoor_keywords
    )

    if indoor_match and outdoor_match:
        return "mixed"

    if indoor_match:
        return "indoor"

    if outdoor_match:
        return "outdoor"

    return "unknown"


def build_activity_intelligence(
    trip: TripRequest,
    research: DestinationResearch,
) -> ActivityIntelligence:
    """
    Convert grounded destination recommendations
    into structured ActivityCandidate objects.
    """

    activities = []

    for recommendation in research.recommendations:

        environment = classify_environment(
            name=recommendation.name,
            category=recommendation.category,
            description=(
                recommendation.why_recommended
            ),
        )

        preference_score = (
            calculate_preference_score(
                name=recommendation.name,
                category=recommendation.category,
                description=(
                    recommendation.why_recommended
                ),
                interests=trip.interests,
            )
        )

        weather_sensitive = (
            environment
            in {
                "outdoor",
                "mixed",
            }
        )

        confidence = (
            0.8
            if recommendation.source_ids
            else 0.4
        )

        activity = ActivityCandidate(
            name=recommendation.name,

            category=recommendation.category,

            description=(
                recommendation.why_recommended
            ),

            latitude=None,
            longitude=None,

            environment=environment,

            estimated_duration_minutes=None,
            estimated_cost=None,

            currency=trip.currency,

            preference_score=(
                preference_score
            ),

            weather_sensitive=(
                weather_sensitive
            ),

            source_ids=(
                recommendation.source_ids
            ),

            confidence=confidence,
        )

        activities.append(
            activity
        )

    return ActivityIntelligence(
        destination=trip.destination,
        activities=activities,
    )