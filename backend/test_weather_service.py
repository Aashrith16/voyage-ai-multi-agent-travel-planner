from datetime import date

from voyage_ai.services.weather_service import (
    get_weather_context,
)


weather = get_weather_context(
    destination="Tokyo",

    start_date=date(
        2026,
        12,
        10,
    ),

    end_date=date(
        2026,
        12,
        16,
    ),
)


print("\n======================================")
print("VOYAGEAI WEATHER INTELLIGENCE")
print("======================================")


print("\nDESTINATION:")
print(weather.destination)


print("\nDATA MODE:")
print(weather.data_mode)


print("\nDISCLAIMER:")
print(weather.disclaimer)


print("\nDAILY WEATHER:")


for day in weather.daily_weather:

    print(
        f"\nDate: {day.date}"
    )

    print(
        f"Max temperature: "
        f"{day.temperature_max_c:.1f} °C"
    )

    print(
        f"Min temperature: "
        f"{day.temperature_min_c:.1f} °C"
    )

    print(
        f"Average precipitation: "
        f"{day.precipitation_mm:.1f} mm"
    )


print("\n======================================")
print("WEATHER RISKS")
print("======================================")


for risk in weather.risks:

    print(
        f"\nDate: {risk.date}"
    )

    print(
        f"Rain risk: "
        f"{risk.rain_risk}"
    )

    print(
        f"Temperature risk: "
        f"{risk.temperature_risk}"
    )

    print(
        f"Outdoor suitability: "
        f"{risk.outdoor_suitability}"
    )

    if risk.reasons:

        print(
            "Reasons: "
            + "; ".join(
                risk.reasons
            )
        )