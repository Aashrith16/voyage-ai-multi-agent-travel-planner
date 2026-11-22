from datetime import date, datetime, timezone
from email.utils import parsedate_to_datetime
from functools import lru_cache
from threading import Lock
import time

import httpx

GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"

_CACHE_TTL_SECONDS = 60 * 60
_MAX_RETRY_ATTEMPTS = 4
_MAX_RETRY_AFTER_SECONDS = 30.0
_response_cache: dict[tuple, tuple[float, dict]] = {}
_cache_guard = Lock()
_request_locks = tuple(Lock() for _ in range(32))


def _retry_delay(response: httpx.Response | None, attempt: int) -> float | None:
    """Return a bounded delay; None means Retry-After exceeds our wait limit."""
    if response is not None:
        retry_after = response.headers.get("Retry-After")
        if retry_after:
            try:
                delay = max(0.0, float(retry_after))
            except ValueError:
                try:
                    retry_at = parsedate_to_datetime(retry_after)
                    if retry_at.tzinfo is None:
                        retry_at = retry_at.replace(tzinfo=timezone.utc)
                    delay = max(0.0, (retry_at - datetime.now(timezone.utc)).total_seconds())
                except (TypeError, ValueError, OverflowError):
                    delay = None
            if delay is not None:
                return delay if delay <= _MAX_RETRY_AFTER_SECONDS else None
    return min(0.5 * (2 ** attempt), 8.0)


def _get_json(url: str, params: dict) -> dict:
    key = (url, tuple(sorted((name, str(value)) for name, value in params.items())))
    # A striped per-request lock coalesces concurrent identical requests without
    # serializing unrelated destinations or date ranges.
    request_lock = _request_locks[hash(key) % len(_request_locks)]
    with request_lock:
        now = time.monotonic()
        with _cache_guard:
            cached = _response_cache.get(key)
            if cached and cached[0] > now:
                return cached[1]
            _response_cache.pop(key, None)

        for attempt in range(_MAX_RETRY_ATTEMPTS):
            try:
                response = httpx.get(url, params=params, timeout=30)
            except httpx.RequestError:
                if attempt == _MAX_RETRY_ATTEMPTS - 1:
                    raise
                time.sleep(_retry_delay(None, attempt))
                continue

            if response.status_code == 429 or response.status_code >= 500:
                if attempt == _MAX_RETRY_ATTEMPTS - 1:
                    response.raise_for_status()
                delay = _retry_delay(response, attempt)
                if delay is None:
                    # Do not retry before the provider's Retry-After instruction.
                    response.raise_for_status()
                time.sleep(delay)
                continue

            response.raise_for_status()
            data = response.json()
            with _cache_guard:
                _response_cache[key] = (time.monotonic() + _CACHE_TTL_SECONDS, data)
            return data
    raise RuntimeError("Weather provider request failed after retries.")


@lru_cache(maxsize=256)
def geocode_city(city: str) -> dict:
    """Resolve a city to its own matching result rather than the first nearby result."""
    query = city.strip()
    if not query:
        raise ValueError("Destination cannot be empty.")
    data = _get_json(GEOCODING_URL, {
        "name": query, "count": 10, "language": "en", "format": "json",
    })
    results = data.get("results", [])
    if not results:
        raise ValueError(f"Could not find coordinates for {city}.")

    # Open-Meteo can return nearby/better-known cities first. Prefer an exact
    # city-name match and, when supplied, the country in the user's query.
    parts = [part.strip().casefold() for part in query.split(",")]
    city_name = parts[0]
    country_hint = parts[-1] if len(parts) > 1 else None
    matching = [item for item in results if item.get("name", "").casefold() == city_name]
    if country_hint:
        country_matches = [item for item in matching if item.get("country", "").casefold() == country_hint]
        if country_matches:
            matching = country_matches
    location = (matching or results)[0]
    return {
        "name": location["name"], "latitude": location["latitude"],
        "longitude": location["longitude"], "country": location.get("country"),
        "timezone": location.get("timezone"),
    }


def get_forecast(latitude: float, longitude: float, start_date: date, end_date: date) -> dict:
    return _get_json(FORECAST_URL, {
        "latitude": latitude, "longitude": longitude,
        "start_date": start_date.isoformat(), "end_date": end_date.isoformat(),
        "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_sum,precipitation_probability_max",
        "timezone": "auto",
    })


def get_historical_weather(latitude: float, longitude: float, start_date: date, end_date: date) -> dict:
    return _get_json(ARCHIVE_URL, {
        "latitude": latitude, "longitude": longitude,
        "start_date": start_date.isoformat(), "end_date": end_date.isoformat(),
        "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_sum",
        "timezone": "auto",
    })
