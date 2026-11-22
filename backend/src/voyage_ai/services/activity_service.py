import re

from voyage_ai.models.activity import (
    ActivityCandidate,
    ActivityIntelligence,
)
from voyage_ai.models.destination import (
    DestinationResearch,
)
from voyage_ai.models.trip import TripRequest


_LODGING_TYPES = {
    "hotel", "hostel", "motel", "guest_house", "guesthouse", "inn",
    "apartment", "chalet", "alpine_hut", "camp_site", "caravan_site",
    "accommodation", "lodging",
}
_SIGHTSEEING_CATEGORIES = {
    "attraction", "sightseeing", "temple", "shrine", "museum",
    "gallery", "park", "garden", "nature", "food", "restaurant", "cafe",
    "market", "shopping", "landmark", "historic", "heritage",
}
_LODGING_NAME_PREFIX = re.compile(
    r"^\s*(?:the\s+)?(?:hotel|hostel|motel|guest\s*house|guesthouse|inn)\b",
    re.IGNORECASE,
)
_LODGING_DESCRIPTION = re.compile(
    r"\b(?:hotel|hostel|motel|guest\s*house|guesthouse|lodging|accommodation)\b"
    r".{0,45}\b(?:rooms?|overnight|stay|check[ -]?in|booking|per night)\b",
    re.IGNORECASE,
)


def is_accommodation_activity(activity: ActivityCandidate) -> bool:
    """Classify lodging without excluding attractions by incidental name text."""
    category_words = {word.casefold() for word in tokenize(activity.category)}
    if category_words & _SIGHTSEEING_CATEGORIES:
        return False
    if category_words & _LODGING_TYPES:
        return True

    resolved_type = (activity.resolved_place_type or "").casefold().replace("-", "_")
    resolved_category = (activity.resolved_place_category or "").casefold()
    if resolved_type in _LODGING_TYPES and resolved_category in {"tourism", "accommodation", "lodging"}:
        return True

    # Name and description checks are fallbacks only when no stronger place
    # category indicates a visitor attraction.
    if _LODGING_NAME_PREFIX.search(activity.name):
        return True
    return bool(_LODGING_DESCRIPTION.search(activity.description))


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
    excluded_accommodation_names = []

    for recommendation in research.recommendations:
        candidate = ActivityCandidate(
            name=recommendation.name,
            category=recommendation.category,
            description=recommendation.why_recommended,
            estimated_duration_minutes=recommendation.estimated_visit_minutes,
            duration_estimate_basis=(
                "activity_specific_ai_estimate"
                if recommendation.estimated_visit_minutes is not None
                else "category_fallback_estimate"
            ),
            currency=trip.currency,
            source_ids=recommendation.source_ids,
            preference_score=calculate_preference_score(
                name=recommendation.name,
                category=recommendation.category,
                description=recommendation.why_recommended,
                interests=trip.interests,
            ),
            environment=classify_environment(
                name=recommendation.name,
                category=recommendation.category,
                description=recommendation.why_recommended,
            ),
            weather_sensitive=False,
            confidence=0.8 if recommendation.source_ids else 0.4,
        )
        if is_accommodation_activity(candidate):
            excluded_accommodation_names.append(candidate.name)
            continue

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

            estimated_duration_minutes=recommendation.estimated_visit_minutes,
            duration_estimate_basis=(
                "activity_specific_ai_estimate"
                if recommendation.estimated_visit_minutes is not None
                else "category_fallback_estimate"
            ),
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
        excluded_accommodation_names=excluded_accommodation_names,
    )
