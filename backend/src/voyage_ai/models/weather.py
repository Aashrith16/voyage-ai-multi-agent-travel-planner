from datetime import date
from typing import Literal

from pydantic import BaseModel, Field


class DailyWeather(BaseModel):
    date: date

    temperature_max_c: float | None = None
    temperature_min_c: float | None = None

    precipitation_mm: float | None = None
    precipitation_probability: float | None = None

    weather_code: int | None = None


class WeatherRisk(BaseModel):
    date: date

    rain_risk: Literal[
        "low",
        "moderate",
        "high",
        "unknown",
    ]

    temperature_risk: Literal[
        "low",
        "moderate",
        "high",
        "unknown",
    ]

    outdoor_suitability: Literal[
        "good",
        "caution",
        "poor",
        "unknown",
    ]

    reasons: list[str] = Field(
        default_factory=list
    )


class WeatherContext(BaseModel):
    destination: str

    latitude: float
    longitude: float

    data_mode: Literal[
        "forecast",
        "seasonal_history",
    ]

    disclaimer: str

    daily_weather: list[DailyWeather]

    risks: list[WeatherRisk]

    summary: str