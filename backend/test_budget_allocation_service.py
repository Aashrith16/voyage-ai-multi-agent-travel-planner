import unittest
from datetime import date

from pydantic import ValidationError

from voyage_ai.models.budget import BudgetCostEstimate
from voyage_ai.models.trip import TripRequest
from voyage_ai.services.budget_service import (
    apply_budget_edits,
    build_budget_allocation,
)


def make_trip(*, travelers=2, days=3, budget=5000):
    return TripRequest(
        origin="Hyderabad",
        destination="Kyoto",
        departure_date=date(2027, 4, 10),
        return_date=date(2027, 4, 10 + days - 1),
        travelers=travelers,
        budget=budget,
        currency="INR",
    )


class BudgetAllocationServiceTests(unittest.TestCase):
    def test_initial_allocation_uses_reserve_and_leaves_unknown_categories_unallocated(self):
        allocation = build_budget_allocation(make_trip(budget=100000), contingency_rate=0.10)

        self.assertEqual(allocation.amount_for("contingency"), 10000)
        self.assertEqual(allocation.amount_for("transportation"), 0)
        self.assertEqual(allocation.amount_for("accommodation"), 0)
        self.assertEqual(allocation.unallocated_balance, 90000)
        self.assertTrue(all(
            line.certainty == "unavailable"
            for line in allocation.categories
            if line.category != "contingency"
        ))

    def test_cost_estimates_scale_with_travellers_and_trip_duration(self):
        allocation = build_budget_allocation(
            make_trip(travelers=2, days=3),
            cost_estimates=[
                BudgetCostEstimate(category="transportation", origin="Hyderabad", destination="Kyoto", amount=50, currency="INR", basis="per_traveler", source="Fare quote"),
                BudgetCostEstimate(category="accommodation", origin="Hyderabad", destination="Kyoto", amount=100, currency="INR", basis="per_night", source="Hotel quote", certainty="confirmed"),
                BudgetCostEstimate(category="food_dining", origin="Hyderabad", destination="Kyoto", amount=10, currency="INR", basis="per_traveler_per_day", source="Meal estimate"),
                BudgetCostEstimate(category="local_transportation", origin="Hyderabad", destination="Kyoto", amount=5, currency="INR", basis="per_day", source="Transit pass estimate"),
                BudgetCostEstimate(category="activities_attractions", origin="Hyderabad", destination="Kyoto", amount=2, currency="INR", basis="per_traveler_per_day", source="Tickets"),
            ],
        )

        self.assertEqual(allocation.amount_for("transportation"), 100)
        self.assertEqual(allocation.amount_for("accommodation"), 200)  # two nights
        self.assertEqual(allocation.amount_for("food_dining"), 60)
        self.assertEqual(allocation.amount_for("local_transportation"), 15)
        self.assertEqual(allocation.amount_for("activities_attractions"), 12)
        self.assertEqual(allocation.categories[1].certainty, "confirmed")

        single_traveler = build_budget_allocation(
            make_trip(travelers=1, days=2),
            cost_estimates=[BudgetCostEstimate(
                category="food_dining", origin="Hyderabad", destination="Kyoto", amount=10, currency="INR",
                basis="per_traveler_per_day", source="Meal estimate",
            )],
        )
        self.assertEqual(single_traveler.amount_for("food_dining"), 20)

    def test_accommodation_units_scale_without_multiplying_room_price_by_travellers(self):
        estimates = [
            BudgetCostEstimate(category="accommodation", origin="Hyderabad", destination="Kyoto", amount=100, currency="INR", basis="per_room_per_night", source="Room"),
            BudgetCostEstimate(category="accommodation", origin="Hyderabad", destination="Kyoto", amount=50, currency="INR", basis="per_traveler_per_night", source="Guest"),
            BudgetCostEstimate(category="accommodation", origin="Hyderabad", destination="Kyoto", amount=40, currency="INR", basis="per_capsule_per_night", source="Capsule"),
        ]
        allocation = build_budget_allocation(make_trip(travelers=2, days=3), estimates)
        self.assertEqual(allocation.amount_for("accommodation"), 560)

    def test_room_and_person_night_multipliers_are_distinct(self):
        room = BudgetCostEstimate(category="accommodation", origin="Hyderabad", destination="Kyoto", amount=100, currency="INR", basis="per_room_per_night", source="Room")
        person = BudgetCostEstimate(category="accommodation", origin="Hyderabad", destination="Kyoto", amount=100, currency="INR", basis="per_traveler_per_night", source="Person")
        room_allocation = build_budget_allocation(make_trip(travelers=2, days=3), [room])
        person_allocation = build_budget_allocation(make_trip(travelers=2, days=3), [person])
        self.assertEqual(room_allocation.amount_for("accommodation"), 200)
        self.assertEqual(person_allocation.amount_for("accommodation"), 400)

    def test_cost_estimate_in_another_currency_is_not_converted_or_used(self):
        allocation = build_budget_allocation(
            make_trip(budget=1000),
            cost_estimates=[BudgetCostEstimate(
                category="transportation", origin="Hyderabad", destination="Kyoto", amount=100, currency="USD",
                basis="per_trip", source="Foreign quote",
            )],
        )

        self.assertEqual(allocation.amount_for("transportation"), 0)
        self.assertIsNone(allocation.categories[0].known_cost_estimate)
        self.assertIn("exchange-rate conversion was guessed", allocation.allocation_note)

    def test_cost_estimates_for_another_trip_are_not_reused(self):
        allocation = build_budget_allocation(
            make_trip(),
            cost_estimates=[BudgetCostEstimate(
                category="transportation", origin="Hyderabad", destination="Jaipur",
                amount=4000, currency="INR", source="Different destination quote",
            )],
        )
        self.assertEqual(allocation.amount_for("transportation"), 0)
        self.assertIn("different origin or destination", allocation.allocation_note)

    def test_manual_edit_updates_only_selected_category_and_remaining_balance(self):
        allocation = build_budget_allocation(make_trip(budget=1000), contingency_rate=0.10)
        first_edit = apply_budget_edits(allocation, {"accommodation": 300})
        updated = apply_budget_edits(first_edit, {"food_dining": 200})

        self.assertEqual(updated.amount_for("accommodation"), 300)
        self.assertEqual(updated.amount_for("food_dining"), 200)
        self.assertEqual(updated.amount_for("transportation"), 0)
        self.assertEqual(updated.amount_for("contingency"), 100)
        self.assertEqual(updated.unallocated_balance, 400)
        self.assertEqual(set(updated.edited_categories), {"accommodation", "food_dining"})

    def test_over_budget_edits_are_rejected(self):
        allocation = build_budget_allocation(make_trip(budget=1000), contingency_rate=0.10)
        with self.assertRaisesRegex(ValueError, "exceed the total trip budget"):
            apply_budget_edits(allocation, {"transportation": 950})

    def test_allocation_model_rejects_non_finite_monetary_values(self):
        with self.assertRaises(ValidationError):
            BudgetCostEstimate(category="transportation", origin="Hyderabad", destination="Kyoto", amount=float("inf"), currency="INR", source="bad")
        with self.assertRaises(ValidationError):
            make_trip(budget=float("inf"))

    def test_manual_category_edits_survive_followup_draft_processing(self):
        from unittest.mock import patch
        from voyage_ai.graph import workflow

        trip = make_trip(budget=1000)
        allocation = apply_budget_edits(
            build_budget_allocation(trip, contingency_rate=0.10),
            {"food_dining": 250},
        )
        previous = trip.model_dump()
        previous["departure_date"] = date(2027, 4, 10)
        from voyage_ai.models.trip import TripRequestDraft

        draft = TripRequestDraft(**previous, missing_fields=[])
        changed = TripRequestDraft(departure_date="2027-04-11")
        state = {
            "draft": draft,
            "followup_input": "Move departure to April 11",
            "budget_allocation": allocation,
        }
        with patch.object(workflow, "understand_trip_request", return_value=changed):
            delta = workflow.process_followup_node(state)

        self.assertEqual(delta["draft"].departure_date, date(2027, 4, 11))
        self.assertEqual(state["budget_allocation"].amount_for("food_dining"), 250)


if __name__ == "__main__":
    unittest.main()
