"""Optional live weather demo and safe weather-value formatter."""
from datetime import date
import os


def format_measurement(value: float | None, unit: str) -> str:
    """Format optional weather data without treating missing values as numbers."""
    if value is None:
        return "Unavailable"
    return f"{value:.1f} {unit}"


def main() -> None:
    if os.getenv("VOYAGEAI_RUN_LIVE_TESTS") != "1":
        print("Live weather demo skipped. Set VOYAGEAI_RUN_LIVE_TESTS=1 to enable provider calls.")
        return

    from voyage_ai.services.weather_service import get_weather_context

    weather = get_weather_context(
        destination="Tokyo",
        start_date=date(2026, 12, 10),
        end_date=date(2026, 12, 16),
    )

    print("\n======================================")
    print("VOYAGEAI WEATHER INTELLIGENCE")
    print("======================================")
    print("\nDESTINATION:", weather.destination)
    print("\nDATA MODE:", weather.data_mode)
    print("\nDISCLAIMER:", weather.disclaimer)
    print("\nDAILY WEATHER:")
    for day in weather.daily_weather:
        print(f"\nDate: {day.date}")
        print("Max temperature:", format_measurement(day.temperature_max_c, "?C"))
        print("Min temperature:", format_measurement(day.temperature_min_c, "?C"))
        print("Average precipitation:", format_measurement(day.precipitation_mm, "mm"))

    print("\n======================================")
    print("WEATHER RISKS")
    print("======================================")
    for risk in weather.risks:
        print(f"\nDate: {risk.date}")
        print("Rain risk:", risk.rain_risk)
        print("Temperature risk:", risk.temperature_risk)
        print("Outdoor suitability:", risk.outdoor_suitability)
        if risk.reasons:
            print("Reasons:", "; ".join(risk.reasons))


if __name__ == "__main__":
    main()
