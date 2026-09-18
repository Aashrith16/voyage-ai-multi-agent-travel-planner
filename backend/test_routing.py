from voyage_ai.tools.place_search import (
    resolve_place,
)
from voyage_ai.tools.routing import (
    get_route_matrix,
)


names = [
    "Akihabara",
    "Ueno Park",
    "Tokyo Skytree",
]


places = []


print(
    "\n======================================"
)

print(
    "RESOLVING PLACES"
)

print(
    "======================================"
)


for name in names:

    place = resolve_place(
        place_name=name,
        destination="Tokyo",
    )

    places.append(
        place
    )

    print(
        f"\n{name}"
    )

    print(
        f"{place.latitude}, "
        f"{place.longitude}"
    )


coordinates = [
    (
        place.latitude,
        place.longitude,
    )
    for place in places
]


print(
    "\n======================================"
)

print(
    "REQUESTING OSRM ROUTE MATRIX"
)

print(
    "======================================"
)


result = get_route_matrix(
    coordinates
)


print(
    "\nRAW DURATIONS (SECONDS)"
)

for row in result["durations"]:
    print(row)


print(
    "\nRAW DISTANCES (METERS)"
)

for row in result["distances"]:
    print(row)