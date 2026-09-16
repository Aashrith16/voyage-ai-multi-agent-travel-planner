from voyage_ai.tools.place_search import (
    resolve_place,
)


place = resolve_place(
    place_name="Akihabara",
    destination="Tokyo",
)


print(
    "\n======================================"
)

print(
    "VOYAGEAI PLACE RESOLUTION"
)

print(
    "======================================"
)


print(
    place.model_dump_json(
        indent=2
    )
)