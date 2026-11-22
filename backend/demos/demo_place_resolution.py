"""Runnable demo; live provider calls require VOYAGEAI_RUN_LIVE_TESTS=1."""
import os


def main() -> None:
    if os.getenv("VOYAGEAI_RUN_LIVE_TESTS") != "1":
        print("Live demo skipped. Set VOYAGEAI_RUN_LIVE_TESTS=1 to enable provider calls.")
        return

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


if __name__ == "__main__":
    main()
