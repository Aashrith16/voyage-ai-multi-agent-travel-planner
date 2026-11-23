"""Cached, configurable geocoding for itinerary places."""

from __future__ import annotations

import logging
import os
import threading
import time
from functools import lru_cache

import httpx

from voyage_ai.models.place import ResolvedPlace


logger = logging.getLogger(__name__)
GEOAPIFY_SEARCH_URL = "https://api.geoapify.com/v1/geocode/search"
NOMINATIM_SEARCH_URL = "https://nominatim.openstreetmap.org/search"
NOMINATIM_MIN_INTERVAL_SECONDS = 1.1

_nominatim_lock = threading.Lock()
_last_nominatim_request_at = 0.0


class PlaceLookupError(RuntimeError):
    """Safe provider failure metadata; never includes request URLs or keys."""

    def __init__(self, provider: str, *, status_code: int | None = None):
        self.provider = provider
        self.status_code = status_code
        super().__init__(f"{provider} geocoding lookup failed.")


class PlaceNotFoundError(PlaceLookupError):
    def __init__(self, provider: str):
        super().__init__(provider)
        self.args = (f"{provider} returned no geocoding result.",)


def build_search_queries(place_name: str, destination: str) -> list[str]:
    """Build a short, ordered set of place-plus-destination queries."""
    original = place_name.strip()
    queries = [f"{original}, {destination}"]
    lowered = original.casefold()

    if lowered.endswith(" area"):
        queries.append(f"{original[:-5].strip()}, {destination}")

    if " in " in lowered:
        first, second = original.split(" in ", 1)
        queries.extend((f"{first.strip()}, {destination}", f"{second.strip()}, {destination}"))

    if "&" in original:
        queries.append(f"{original.split('&', 1)[0].strip()}, {destination}")

    first_words = original.split()[:2]
    if first_words:
        queries.append(f"{' '.join(first_words)}, {destination}")
    return list(dict.fromkeys(query for query in queries if query.strip()))


def _configured_provider() -> str:
    provider = os.getenv("GEOCODING_PROVIDER", "auto").strip().casefold()
    if provider not in {"auto", "geoapify", "nominatim"}:
        raise ValueError("GEOCODING_PROVIDER must be auto, geoapify, or nominatim.")
    if provider == "auto":
        return "geoapify" if os.getenv("GEOAPIFY_API_KEY", "").strip() else "nominatim"
    if provider == "geoapify" and not os.getenv("GEOAPIFY_API_KEY", "").strip():
        raise ValueError("GEOAPIFY_API_KEY is required when GEOCODING_PROVIDER=geoapify.")
    return provider


def _nominatim_headers(user_agent: str) -> dict[str, str]:
    # Nominatim requires a real application-identifying User-Agent. Set a
    # contact-bearing value in production, for example VoyageAI/1.0 (+mailto:...).
    return {"User-Agent": user_agent.strip() or "VoyageAI/1.0"}


def _wait_for_nominatim_slot() -> None:
    """Enforce at most one public Nominatim request per 1.1 seconds per process."""
    global _last_nominatim_request_at
    with _nominatim_lock:
        now = time.monotonic()
        delay = NOMINATIM_MIN_INTERVAL_SECONDS - (now - _last_nominatim_request_at)
        if delay > 0:
            time.sleep(delay)
        _last_nominatim_request_at = time.monotonic()


def _safe_http_get(provider: str, url: str, *, params: dict, headers: dict | None = None) -> httpx.Response:
    try:
        response = httpx.get(url, params=params, headers=headers, timeout=10)
    except httpx.TimeoutException:
        raise PlaceLookupError(provider) from None
    except httpx.RequestError:
        raise PlaceLookupError(provider) from None

    if response.status_code >= 400:
        # In particular, 429/629 is never retried with another query against
        # Nominatim. A provider may include query parameters in its URL, so do
        # not propagate or log the HTTP client's exception text.
        raise PlaceLookupError(provider, status_code=response.status_code)
    return response


def _geoapify_lookup(place_name: str, destination: str, api_key: str) -> ResolvedPlace:
    query = f"{place_name.strip()}, {destination.strip()}"
    response = _safe_http_get(
        "geoapify",
        GEOAPIFY_SEARCH_URL,
        params={"text": query, "format": "json", "limit": 1, "apiKey": api_key},
    )
    try:
        results = response.json().get("results", [])
        if not results:
            raise PlaceNotFoundError("geoapify")
        result = results[0]
        latitude = float(result["lat"])
        longitude = float(result["lon"])
        if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
            raise ValueError("out-of-range coordinates")
        category = result.get("category") or result.get("datasource", {}).get("sourcename")
        if isinstance(category, list):
            category = ",".join(str(item) for item in category)
        importance = result.get("rank", {}).get("confidence")
        return ResolvedPlace(
            query=query,
            name=place_name,
            display_name=str(result.get("formatted") or result.get("address_line1") or query),
            latitude=latitude,
            longitude=longitude,
            category=str(category) if category else None,
            place_type=result.get("result_type"),
            importance=float(importance) if importance is not None else None,
        )
    except PlaceNotFoundError:
        raise
    except (KeyError, TypeError, ValueError, AttributeError):
        raise PlaceLookupError("geoapify") from None


def _nominatim_lookup(
    place_name: str,
    destination: str,
    *,
    user_agent: str,
    contact: str,
) -> ResolvedPlace:
    last_query = f"{place_name.strip()}, {destination.strip()}"
    for query in build_search_queries(place_name, destination):
        _wait_for_nominatim_slot()
        params = {
            "q": query,
            "format": "jsonv2",
            "limit": 1,
            "addressdetails": 1,
            "extratags": 1,
        }
        if contact.strip():
            params["email"] = contact.strip()

        response = _safe_http_get(
            "nominatim",
            NOMINATIM_SEARCH_URL,
            params=params,
            headers=_nominatim_headers(user_agent),
        )
        try:
            results = response.json()
            if not results:
                last_query = query
                continue
            result = results[0]
            latitude = float(result["lat"])
            longitude = float(result["lon"])
            if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
                raise ValueError("out-of-range coordinates")
            return ResolvedPlace(
                query=query,
                name=place_name,
                display_name=result["display_name"],
                latitude=latitude,
                longitude=longitude,
                osm_type=result.get("osm_type"),
                osm_id=result.get("osm_id"),
                category=result.get("category"),
                place_type=result.get("type"),
                importance=result.get("importance"),
            )
        except (KeyError, TypeError, ValueError, AttributeError):
            raise PlaceLookupError("nominatim") from None
    raise PlaceNotFoundError("nominatim")


@lru_cache(maxsize=1024)
def _resolve_place_cached(
    place_name: str,
    destination: str,
    provider: str,
    allow_nominatim_fallback: bool,
    nominatim_user_agent: str,
    nominatim_contact: str,
) -> ResolvedPlace:
    if provider == "nominatim":
        return _nominatim_lookup(
            place_name,
            destination,
            user_agent=nominatim_user_agent,
            contact=nominatim_contact,
        )

    api_key = os.getenv("GEOAPIFY_API_KEY", "").strip()
    if not api_key:
        raise ValueError("GEOAPIFY_API_KEY is required when GEOCODING_PROVIDER=geoapify.")
    try:
        return _geoapify_lookup(place_name, destination, api_key)
    except (PlaceLookupError, PlaceNotFoundError) as error:
        if not allow_nominatim_fallback or error.status_code in {429, 629}:
            raise
        logger.warning(
            "Geoapify lookup failed; using configured Nominatim fallback "
            "(error_type=%s status_code=%s)",
            type(error).__name__,
            error.status_code,
        )
        return _nominatim_lookup(
            place_name,
            destination,
            user_agent=nominatim_user_agent,
            contact=nominatim_contact,
        )


def resolve_place(place_name: str, destination: str) -> ResolvedPlace:
    """Resolve and cache a place; failed lookups are not cached."""
    provider = _configured_provider()
    allow_fallback = os.getenv("GEOCODING_NOMINATIM_FALLBACK", "false").strip().casefold() in {
        "1", "true", "yes", "on",
    }
    return _resolve_place_cached(
        place_name.strip(),
        destination.strip(),
        provider,
        allow_fallback,
        os.getenv("NOMINATIM_USER_AGENT", "VoyageAI/1.0"),
        os.getenv("NOMINATIM_CONTACT", ""),
    )


def clear_place_cache() -> None:
    """Clear successful in-process lookups, primarily for tests/maintenance."""
    _resolve_place_cached.cache_clear()
