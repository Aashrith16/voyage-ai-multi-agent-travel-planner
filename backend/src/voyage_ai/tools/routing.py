import httpx


OSRM_BASE_URL = (
    "https://router.project-osrm.org"
)


def get_route_matrix(
    coordinates: list[
        tuple[float, float]
    ],
) -> dict:
    """
    Get road-network travel durations and
    distances between all supplied locations.

    Coordinates must be:
        (latitude, longitude)

    OSRM URL requires:
        longitude,latitude
    """

    if len(coordinates) < 2:
        raise ValueError(
            "At least two coordinates "
            "are required."
        )


    coordinate_string = ";".join(
        f"{longitude},{latitude}"
        for latitude, longitude
        in coordinates
    )


    url = (
        f"{OSRM_BASE_URL}"
        f"/table/v1/driving/"
        f"{coordinate_string}"
    )


    response = httpx.get(
        url,
        params={
            "annotations":
                "duration,distance",
        },
        timeout=30,
    )


    response.raise_for_status()

    data = response.json()


    if data.get("code") != "Ok":
        raise RuntimeError(
            "OSRM routing failed: "
            f"{data.get('code')}"
        )


    return data