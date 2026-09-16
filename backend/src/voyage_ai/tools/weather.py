from datetime import date

import httpx


# --------------------------------------------------
# OPEN-METEO API URLS
# --------------------------------------------------

GEOCODING_URL = (
    "https://geocoding-api.open-meteo.com/v1/search"
)

FORECAST_URL = (
    "https://api.open-meteo.com/v1/forecast"
)

ARCHIVE_URL = (
    "https://archive-api.open-meteo.com/v1/archive"
)


# --------------------------------------------------
# TOOL 1
# Convert city name → latitude and longitude
# --------------------------------------------------

def geocode_city(city: str) -> dict:
    """
    Convert a city name such as 'Tokyo'
    into latitude and longitude.
    """

    response = httpx.get(
        GEOCODING_URL,
        params={
            "name": city,
            "count": 1,
            "language": "en",
            "format": "json",
        },
        timeout=20,
    )

    # Raise an error if the API request failed.
    response.raise_for_status()

    data = response.json()

    results = data.get("results", [])

    if not results:
        raise ValueError(
            f"Could not find coordinates for {city}."
        )

    location = results[0]

    return {
        "name": location["name"],
        "latitude": location["latitude"],
        "longitude": location["longitude"],
        "country": location.get("country"),
        "timezone": location.get("timezone"),
    }


# --------------------------------------------------
# TOOL 2
# Get actual weather forecast
# --------------------------------------------------

def get_forecast(
    latitude: float,
    longitude: float,
    start_date: date,
    end_date: date,
) -> dict:
    """
    Get weather forecast data for a location
    between the requested dates.
    """

    response = httpx.get(
        FORECAST_URL,
        params={
            "latitude": latitude,
            "longitude": longitude,

            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),

            "daily": ",".join(
                [
                    "weather_code",
                    "temperature_2m_max",
                    "temperature_2m_min",
                    "precipitation_sum",
                    "precipitation_probability_max",
                ]
            ),

            "timezone": "auto",
        },
        timeout=30,
    )

    response.raise_for_status()

    return response.json()


# --------------------------------------------------
# TOOL 3
# Get historical weather
# --------------------------------------------------

def get_historical_weather(
    latitude: float,
    longitude: float,
    start_date: date,
    end_date: date,
) -> dict:
    """
    Get historical weather for a location
    between the requested dates.
    """

    response = httpx.get(
        ARCHIVE_URL,
        params={
            "latitude": latitude,
            "longitude": longitude,

            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),

            "daily": ",".join(
                [
                    "weather_code",
                    "temperature_2m_max",
                    "temperature_2m_min",
                    "precipitation_sum",
                ]
            ),

            "timezone": "auto",
        },
        timeout=30,
    )

    response.raise_for_status()

    return response.json()
    