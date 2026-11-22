import os
from math import isfinite

from voyage_ai.models.budget import (
    BudgetAllocation,
    BudgetCategory,
    BudgetCategoryAllocation,
    BudgetCostEstimate,
)
from voyage_ai.models.trip import TripRequest


DEFAULT_CONTINGENCY_RATE = 0.10
CATEGORY_LABELS = {
    "transportation": "Transportation",
    "accommodation": "Accommodation",
    "food_dining": "Food and dining",
    "local_transportation": "Local transportation",
    "activities_attractions": "Activities and attractions",
    "contingency": "Emergency / contingency reserve",
}
ALLOCATION_CATEGORIES: tuple[BudgetCategory, ...] = tuple(CATEGORY_LABELS)


def get_contingency_rate() -> float:
    configured = os.getenv("BUDGET_CONTINGENCY_RATE")
    if configured is None:
        return DEFAULT_CONTINGENCY_RATE
    try:
        rate = float(configured)
    except ValueError as error:
        raise ValueError("BUDGET_CONTINGENCY_RATE must be a number from 0 to 1.") from error
    if not isfinite(rate) or not 0 <= rate <= 1:
        raise ValueError("BUDGET_CONTINGENCY_RATE must be a number from 0 to 1.")
    return rate


def _scaled_cost(cost: BudgetCostEstimate, trip: TripRequest, trip_days: int) -> float:
    return _scaled_amount(cost.amount, cost.basis, trip, trip_days, cost.traveler_count_override, cost.quantity_override)


def _scaled_low_cost(cost: BudgetCostEstimate, trip: TripRequest, trip_days: int) -> float:
    return _scaled_amount(
        cost.amount if cost.amount_min is None else cost.amount_min,
        cost.basis,
        trip,
        trip_days,
        cost.traveler_count_override,
        cost.quantity_override,
    )


def _scaled_amount(
    amount: float,
    basis: str,
    trip: TripRequest,
    trip_days: int,
    traveler_count_override: int | None = None,
    quantity_override: int | None = None,
) -> float:
    nights = max((trip.return_date - trip.departure_date).days, 0)
    travelers = traveler_count_override or trip.travelers
    multipliers = {
        "per_trip": 1,
        "per_traveler": travelers,
        "per_admission": travelers,
        "per_day": trip_days,
        "per_night": nights,
        "per_room_per_night": nights,
        "per_capsule_per_night": travelers * nights,
        "per_person_per_room_per_night": travelers * nights,
        "per_traveler_per_day": travelers * trip_days,
        "per_traveler_per_night": travelers * nights,
        "per_ride": quantity_override,
    }
    if basis not in multipliers:
        raise ValueError(f"Cost basis {basis} cannot be scaled without a known quantity.")
    return round(amount * multipliers[basis], 2)


def build_budget_allocation(
    trip: TripRequest,
    cost_estimates: list[BudgetCostEstimate] | None = None,
    contingency_rate: float | None = None,
) -> BudgetAllocation:
    """Build category caps from sourced costs; unsupported costs stay unallocated."""
    rate = get_contingency_rate() if contingency_rate is None else contingency_rate
    if not isfinite(rate) or not 0 <= rate <= 1:
        raise ValueError("Contingency rate must be between 0 and 1.")

    trip_days = (trip.return_date - trip.departure_date).days + 1
    contingency = round(trip.budget * rate, 2)
    evidence: dict[BudgetCategory, list[tuple[float, BudgetCostEstimate]]] = {
        category: [] for category in ALLOCATION_CATEGORIES
    }
    all_evidence: dict[BudgetCategory, list[BudgetCostEstimate]] = {
        category: [] for category in ALLOCATION_CATEGORIES
    }
    incompatible_currency_count = 0
    unrelated_trip_count = 0
    unknown_quantity_count = 0
    for cost in cost_estimates or []:
        if cost.category == "contingency":
            raise ValueError("Contingency is configured by the reserve rate, not a cost estimate.")
        if (
            cost.origin.casefold() != trip.origin.casefold()
            or cost.destination.casefold() != trip.destination.casefold()
        ):
            unrelated_trip_count += 1
            continue
        all_evidence[cost.category].append(cost)
        if cost.currency != trip.currency:
            incompatible_currency_count += 1
            continue
        if cost.basis == "per_ride" and cost.quantity_override is None:
            unknown_quantity_count += 1
            continue
        evidence[cost.category].append((_scaled_cost(cost, trip, trip_days), cost))

    estimates = {
        category: round(sum(amount for amount, _ in rows), 2)
        for category, rows in evidence.items()
    }
    low_estimates = {
        category: round(sum(_scaled_low_cost(cost, trip, trip_days) for _, cost in rows), 2)
        for category, rows in evidence.items()
    }
    evidenced_total = sum(estimates.values())
    notes = []
    if incompatible_currency_count:
        notes.append(
            f"{incompatible_currency_count} cost input(s) in a different currency were excluded; "
            "no exchange-rate conversion was guessed."
        )
    if unknown_quantity_count:
        notes.append(
            f"{unknown_quantity_count} per-ride cost input(s) remain unallocated because the trip has no specified ride count."
        )
    if unrelated_trip_count:
        notes.append(
            f"{unrelated_trip_count} cost input(s) for a different origin or destination were excluded."
        )
    can_recommend_all = evidenced_total + contingency <= trip.budget + 0.01
    if not can_recommend_all:
        notes.append(
            "Available sourced estimates exceed the trip budget after the contingency reserve. "
            "Category caps are left for your review; reduce costs or increase the total budget."
        )

    categories = []
    for category in ALLOCATION_CATEGORIES:
        rows = evidence[category]
        known_estimate = estimates[category] if rows else None
        certainty = (
            "confirmed" if rows and all(cost.certainty == "confirmed" for _, cost in rows)
            else "estimated" if rows
            else "unavailable"
        )
        recommended = contingency if category == "contingency" else (
            known_estimate if can_recommend_all and known_estimate is not None else 0.0
        )
        categories.append(BudgetCategoryAllocation(
            category=category,
            label=CATEGORY_LABELS[category],
            allocated_amount=recommended,
            known_cost_estimate=known_estimate,
            known_cost_estimate_min=low_estimates[category] if rows else None,
            certainty=certainty if category != "contingency" else "estimated",
            sources=list(dict.fromkeys(cost.source for cost in all_evidence[category])),
            cost_evidence=all_evidence[category],
        ))

    allocated_total = round(sum(item.allocated_amount for item in categories), 2)
    if allocated_total > trip.budget + 0.01:
        raise ValueError("The contingency reserve exceeds the total trip budget.")
    unavailable = [
        CATEGORY_LABELS[category]
        for category in ALLOCATION_CATEGORIES
        if category != "contingency" and not evidence[category]
    ]
    if unavailable:
        notes.append(
            "No sourced prices are available for "
            + ", ".join(unavailable)
            + ". Those category caps remain unallocated; enter amounts before confirming."
        )
    return BudgetAllocation(
        origin=trip.origin,
        destination=trip.destination,
        total_budget=trip.budget,
        currency=trip.currency,
        travelers=trip.travelers,
        trip_days=trip_days,
        contingency_rate=rate,
        categories=categories,
        unallocated_balance=round(trip.budget - allocated_total, 2),
        allocation_note=" ".join(notes),
    )


def apply_budget_edits(
    allocation: BudgetAllocation,
    edits: dict[str, float],
) -> BudgetAllocation:
    """Apply only submitted categories, preserving every other category as-is."""
    unknown = set(edits) - set(ALLOCATION_CATEGORIES)
    if unknown:
        raise ValueError(f"Unknown budget categories: {', '.join(sorted(unknown))}.")

    amounts: dict[str, float] = {
        category.category: category.allocated_amount
        for category in allocation.categories
    }
    edited = set(allocation.edited_categories)
    for category, raw_amount in edits.items():
        if isinstance(raw_amount, bool):
            raise ValueError(f"Allocation for {category} must be a monetary amount, not a boolean.")
        try:
            amount = float(raw_amount)
        except (TypeError, ValueError) as error:
            raise ValueError(f"Allocation for {category} must be a valid amount.") from error
        if not isfinite(amount) or amount < 0:
            raise ValueError(f"Allocation for {category} must be finite and non-negative.")
        amount = round(amount, 2)
        if amount != amounts[category]:
            edited.add(category)  # type: ignore[arg-type]
        amounts[category] = amount

    total_allocated = round(sum(amounts.values()), 2)
    if total_allocated > allocation.total_budget + 0.01:
        raise ValueError(
            f"Category allocations ({total_allocated:.2f} {allocation.currency}) exceed "
            f"the total trip budget ({allocation.total_budget:.2f} {allocation.currency})."
        )

    data = allocation.model_dump()
    data["categories"] = [
        {**item.model_dump(), "allocated_amount": amounts[item.category]}
        for item in allocation.categories
    ]
    data["unallocated_balance"] = round(allocation.total_budget - total_allocated, 2)
    data["edited_categories"] = sorted(edited)
    return BudgetAllocation.model_validate(data)
