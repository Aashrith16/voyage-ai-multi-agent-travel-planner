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


@lru_cache(maxsize=256)
def resolve_place(
    place_name: str,
    destination: str,
) -> ResolvedPlace:
    """
    Resolve a real place name into verified
    geographic information using Nominatim.

    Example:
        Akihabara + Tokyo
            ->
        latitude + longitude
    """

    query = (
        f"{place_name}, {destination}"
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