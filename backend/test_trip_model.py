from voyage_ai.models.trip import TripRequest


trip = TripRequest(
    origin="Hyderabad",
    destination="Tokyo",
    departure_date="2026-12-10",
    return_date="2026-12-16",
    travelers=2,
    budget=250000,
    interests=[
        "anime",
        "technology",
        "food",
    ],
)

print("\n--- TRIP OBJECT ---")
print(trip)

print("\n--- DESTINATION ---")
print(trip.destination)

print("\n--- BUDGET ---")
print(trip.budget)

print("\n--- INTERESTS ---")
print(trip.interests)

print("\n--- JSON OUTPUT ---")
print(trip.model_dump_json(indent=2))