from datetime import date, timedelta

from voyage_ai.models.weather import (
    DailyWeather,
    WeatherContext,
    WeatherRisk,
)
from voyage_ai.tools.weather import (
    geocode_city,
    get_forecast,
    get_historical_weather,
)


# --------------------------------------------------
# SETTINGS
# --------------------------------------------------

FORECAST_HORIZON_DAYS = 16

HISTORICAL_YEARS = 5


# --------------------------------------------------
# WEATHER RISK CLASSIFICATION
# --------------------------------------------------

def classify_weather_risk(
    weather: DailyWeather,
) -> WeatherRisk:
    """
    Convert weather values into simple planning risks.

    These thresholds are VoyageAI planning heuristics,
    not official meteorological warning levels.
    """

    reasons: list[str] = []


    # ----------------------------------------------
    # RAIN RISK
    # ----------------------------------------------

    if weather.precipitation_probability is not None:

        if weather.precipitation_probability >= 70:
            rain_risk = "high"

            reasons.append(
                "High probability of precipitation."
            )

        elif weather.precipitation_probability >= 40:
            rain_risk = "moderate"

            reasons.append(
                "Moderate probability of precipitation."
            )

        else:
            rain_risk = "low"


    elif weather.precipitation_mm is not None:

        if weather.precipitation_mm >= 10:
            rain_risk = "high"

            reasons.append(
                "Historically high precipitation for this period."
            )

        elif weather.precipitation_mm >= 2:
            rain_risk = "moderate"

            reasons.append(
                "Some precipitation is typical for this period."
            )

        else:
            rain_risk = "low"

    else:
        rain_risk = "unknown"


    # ----------------------------------------------
    # TEMPERATURE RISK
    # ----------------------------------------------

    max_temp = weather.temperature_max_c
    min_temp = weather.temperature_min_c


    if max_temp is None or min_temp is None:
        temperature_risk = "unknown"

    elif max_temp >= 35 or min_temp <= 0:
        temperature_risk = "high"

        reasons.append(
            "Potential temperature extremes may affect outdoor plans."
        )

    elif max_temp >= 30 or min_temp <= 5:
        temperature_risk = "moderate"

        reasons.append(
            "Temperature may reduce outdoor comfort."
        )

    else:
        temperature_risk = "low"


    # ----------------------------------------------
    # OUTDOOR SUITABILITY
    # ----------------------------------------------

    if (
        rain_risk == "high"
        or temperature_risk == "high"
    ):
        outdoor_suitability = "poor"

    elif (
        rain_risk == "moderate"
        or temperature_risk == "moderate"
    ):
        outdoor_suitability = "caution"

    elif (
        rain_risk == "unknown"
        or temperature_risk == "unknown"
    ):
        outdoor_suitability = "unknown"

    else:
        outdoor_suitability = "good"


    return WeatherRisk(
        date=weather.date,
        rain_risk=rain_risk,
        temperature_risk=temperature_risk,
        outdoor_suitability=outdoor_suitability,
        reasons=reasons,
    )


# --------------------------------------------------
# FORECAST MODE
# --------------------------------------------------

def build_forecast_context(
    destination: str,
    latitude: float,
    longitude: float,
    start_date: date,
    end_date: date,
) -> WeatherContext:

    raw = get_forecast(
        latitude=latitude,
        longitude=longitude,
        start_date=start_date,
        end_date=end_date,
    )

    daily = raw["daily"]

    weather_days: list[DailyWeather] = []


    for index, day in enumerate(
        daily["time"]
    ):
        weather_days.append(
            DailyWeather(
                date=day,

                temperature_max_c=(
                    daily["temperature_2m_max"][index]
                ),

                temperature_min_c=(
                    daily["temperature_2m_min"][index]
                ),

                precipitation_mm=(
                    daily["precipitation_sum"][index]
                ),

                precipitation_probability=(
                    daily[
                        "precipitation_probability_max"
                    ][index]
                ),

                weather_code=(
                    daily["weather_code"][index]
                ),
            )
        )


    risks = [
        classify_weather_risk(day)
        for day in weather_days
    ]


    return WeatherContext(
        destination=destination,
        latitude=latitude,
        longitude=longitude,

        data_mode="forecast",

        disclaimer=(
            "This uses forecast weather data available "
            "for the requested travel dates. Forecasts "
            "may change as the trip approaches."
        ),

        daily_weather=weather_days,
        risks=risks,

        summary=(
            "Forecast weather context generated "
            "for itinerary planning."
        ),
    )


# --------------------------------------------------
# HELPER FOR HISTORICAL YEARS
# --------------------------------------------------

def replace_year_safely(
    value: date,
    year: int,
) -> date:
    """
    Replace the year safely.

    Handles February 29 by falling back to February 28
    when the historical year is not a leap year.
    """

    try:
        return value.replace(year=year)

    except ValueError:
        return value.replace(
            year=year,
            day=28,
        )


# --------------------------------------------------
# SEASONAL / HISTORICAL MODE
# --------------------------------------------------

def build_seasonal_context(
    destination: str,
    latitude: float,
    longitude: float,
    start_date: date,
    end_date: date,
) -> WeatherContext:

    historical_sets = []

    current_year = date.today().year


    for offset in range(
        1,
        HISTORICAL_YEARS + 1,
    ):
        historical_year = (
            current_year - offset
        )

        historical_start = (
            replace_year_safely(
                start_date,
                historical_year,
            )
        )

        historical_end = (
            replace_year_safely(
                end_date,
                historical_year,
            )
        )

        historical_data = (
            get_historical_weather(
                latitude=latitude,
                longitude=longitude,
                start_date=historical_start,
                end_date=historical_end,
            )
        )

        historical_sets.append(
            historical_data
        )


    number_of_days = (
        (end_date - start_date).days + 1
    )

    weather_days: list[DailyWeather] = []


    for day_index in range(
        number_of_days
    ):
        max_temperatures = []
        min_temperatures = []
        precipitation_values = []


        for dataset in historical_sets:

            daily = dataset["daily"]

            max_value = (
                daily["temperature_2m_max"][
                    day_index
                ]
            )

            min_value = (
                daily["temperature_2m_min"][
                    day_index
                ]
            )

            precipitation_value = (
                daily["precipitation_sum"][
                    day_index
                ]
            )


            if max_value is not None:
                max_temperatures.append(
                    max_value
                )

            if min_value is not None:
                min_temperatures.append(
                    min_value
                )

            if precipitation_value is not None:
                precipitation_values.append(
                    precipitation_value
                )


        target_day = (
            start_date
            + timedelta(days=day_index)
        )


        weather_days.append(
            DailyWeather(
                date=target_day,

                temperature_max_c=(
                    sum(max_temperatures)
                    / len(max_temperatures)
                    if max_temperatures
                    else None
                ),

                temperature_min_c=(
                    sum(min_temperatures)
                    / len(min_temperatures)
                    if min_temperatures
                    else None
                ),

                precipitation_mm=(
                    sum(precipitation_values)
                    / len(precipitation_values)
                    if precipitation_values
                    else None
                ),

                precipitation_probability=None,

                # Weather code is categorical,
                # so we do NOT average it.
                weather_code=None,
            )
        )


    risks = [
        classify_weather_risk(day)
        for day in weather_days
    ]


    return WeatherContext(
        destination=destination,
        latitude=latitude,
        longitude=longitude,

        data_mode="seasonal_history",

        disclaimer=(
            "Exact forecast data is not yet available "
            "for these travel dates. These values are "
            "averages from the same calendar period "
            f"across the previous {HISTORICAL_YEARS} years. "
            "They provide seasonal context and must NOT "
            "be treated as a weather forecast."
        ),

        daily_weather=weather_days,
        risks=risks,

        summary=(
            "Historical seasonal weather context "
            "generated for long-range trip planning."
        ),
    )


# --------------------------------------------------
# MAIN WEATHER INTELLIGENCE FUNCTION
# --------------------------------------------------

def get_weather_context(
    destination: str,
    start_date: date,
    end_date: date,
) -> WeatherContext:
    """
    Automatically choose between:

    1. Real forecast data
    2. Historical seasonal context
    """

    if end_date < start_date:
        raise ValueError(
            "End date cannot be before start date."
        )


    location = geocode_city(
        destination
    )

    latitude = location["latitude"]
    longitude = location["longitude"]


    today = date.today()

    start_days_away = (
        start_date - today
    ).days

    end_days_away = (
        end_date - today
    ).days


    # Use forecast only when the ENTIRE trip
    # fits inside the available forecast window.
    if (
        start_days_away >= 0
        and end_days_away
        <= FORECAST_HORIZON_DAYS
    ):

        return build_forecast_context(
            destination=destination,
            latitude=latitude,
            longitude=longitude,
            start_date=start_date,
            end_date=end_date,
        )


    return build_seasonal_context(
        destination=destination,
        latitude=latitude,
        longitude=longitude,
        start_date=start_date,
        end_date=end_date,
    )