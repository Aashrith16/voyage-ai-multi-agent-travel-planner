from pydantic import BaseModel, Field


class RouteInfo(BaseModel):
    """
    Travel information between two places.
    """

    origin: str
    destination: str

    distance_km: float = Field(
        ge=0,
    )

    duration_minutes: float = Field(
        ge=0,
    )


class TravelMatrix(BaseModel):
    """
    Pairwise travel distances and durations
    between all activity locations.
    """

    locations: list[str]

    durations_minutes: list[list[float | None]]

    distances_km: list[list[float | None]]