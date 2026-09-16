from pydantic import BaseModel, Field


class ResolvedPlace(BaseModel):
    """
    A real geographic place resolved from
    OpenStreetMap / Nominatim.
    """

    query: str

    name: str

    display_name: str

    latitude: float = Field(
        ge=-90,
        le=90,
    )

    longitude: float = Field(
        ge=-180,
        le=180,
    )

    osm_type: str | None = None

    osm_id: int | None = None

    category: str | None = None

    place_type: str | None = None

    importance: float | None = None