import time
from functools import lru_cache

import httpx

from voyage_ai.models.place import (
    ResolvedPlace,
)


NOMINATIM_SEARCH_URL = (
    "https://nominatim.openstreetmap.org/search"
)


HEADERS = {
    "User-Agent": (
        "VoyageAI/0.1 "
        "(student multi-agent travel planner)"
    )
}

def build_search_queries(
    place_name: str,
    destination: str,
) -> list[str]:
    """
    Generate progressively simpler geocoding queries.

    Example:
    'Character Street in Tokyo Station'
        ↓
    'Character Street in Tokyo Station, Tokyo'
    'Character Street, Tokyo'
    'Tokyo Station, Tokyo'
    """

    queries = []

    original = place_name.strip()

    queries.append(
        f"{original}, {destination}"
    )

    lowered = original.lower()

    # Remove descriptive suffix like "Area"
    if lowered.endswith(" area"):

        cleaner = original[:-5].strip()

        queries.append(
            f"{cleaner}, {destination}"
        )

    # Handle phrases like:
    # "Character Street in Tokyo Station"
    if " in " in lowered:

        parts = original.split(" in ", 1)

        first_part = parts[0].strip()
        second_part = parts[1].strip()

        queries.append(
            f"{first_part}, {destination}"
        )

        queries.append(
            f"{second_part}, {destination}"
        )

    # Handle descriptive combinations
    # such as "Akihabara Kaiten Sushi & Izakayas"
    if "&" in original:

        first_part = original.split(
            "&",
            1,
        )[0].strip()

        queries.append(
            f"{first_part}, {destination}"
        )

    # Final broad fallback
    first_words = original.split()[:2]

    if first_words:

        queries.append(
            f"{' '.join(first_words)}, "
            f"{destination}"
        )

    # Remove duplicates while preserving order
    return list(
        dict.fromkeys(
            queries
        )
    )


@lru_cache(maxsize=256)
def resolve_place(
    place_name: str,
    destination: str,
) -> ResolvedPlace:
    """
    Resolve a place using multiple progressively
    simpler Nominatim queries.
    """

    queries = build_search_queries(
        place_name=place_name,
        destination=destination,
    )

    last_error = None

    for query in queries:

        try:

            time.sleep(1.1)

            response = httpx.get(
                NOMINATIM_SEARCH_URL,

                params={
                    "q": query,
                    "format": "jsonv2",
                    "limit": 1,
                    "addressdetails": 1,
                    "extratags": 1,
                },

                headers=HEADERS,

                timeout=30,
            )

            response.raise_for_status()

            results = response.json()

            if not results:
                continue

            result = results[0]

            return ResolvedPlace(
                query=query,

                name=place_name,

                display_name=(
                    result["display_name"]
                ),

                latitude=float(
                    result["lat"]
                ),

                longitude=float(
                    result["lon"]
                ),

                osm_type=result.get(
                    "osm_type"
                ),

                osm_id=result.get(
                    "osm_id"
                ),

                category=result.get(
                    "category"
                ),

                place_type=result.get(
                    "type"
                ),

                importance=result.get(
                    "importance"
                ),
            )

        except Exception as error:

            last_error = error

            continue


    if last_error:

        raise ValueError(
            f"Could not resolve place: "
            f"{place_name} in {destination}. "
            f"Last error: {last_error}"
        )

    raise ValueError(
        f"Could not resolve place: "
        f"{place_name} in {destination}"
    )


    # ---------------------------------------------
    # Nominatim public API usage requirement:
    # keep requests below 1 request per second.
    # ---------------------------------------------

    time.sleep(1.1)


    response = httpx.get(
        NOMINATIM_SEARCH_URL,

        params={
            "q": query,

            "format": "jsonv2",

            "limit": 1,

            "addressdetails": 1,

            "extratags": 1,
        },

        headers=HEADERS,

        timeout=30,
    )


    response.raise_for_status()


    results = response.json()


    if not results:
        raise ValueError(
            f"Could not resolve place: "
            f"{place_name} in {destination}"
        )


    result = results[0]


    return ResolvedPlace(
        query=query,

        name=place_name,

        display_name=(
            result["display_name"]
        ),

        latitude=float(
            result["lat"]
        ),

        longitude=float(
            result["lon"]
        ),

        osm_type=result.get(
            "osm_type"
        ),

        osm_id=result.get(
            "osm_id"
        ),

        category=result.get(
            "category"
        ),

        place_type=result.get(
            "type"
        ),

        importance=result.get(
            "importance"
        ),
    )