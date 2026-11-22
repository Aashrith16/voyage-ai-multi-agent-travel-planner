import unittest
from datetime import date

from voyage_ai.models.activity import ActivityCandidate, ActivityIntelligence
from voyage_ai.models.trip import TripRequest
from voyage_ai.services.cost_research_service import research_trip_costs, resolve_cost_option_selections
from voyage_ai.services.budget_service import build_budget_allocation


def trip(currency="INR", travelers=2, days=4):
    return TripRequest(
        origin="Hyderabad", destination="Kyoto", departure_date=date(2027, 4, 1),
        return_date=date(2027, 4, days), travelers=travelers, budget=100000,
        currency=currency,
    )


class CostResearchTests(unittest.TestCase):
    def search_category(self, category, rows):
        def search(query, **_):
            return rows if f"[CATEGORY:{category}]" in query else []
        return search

    def test_extracts_explicit_cost_range_and_provenance(self):
        result = research_trip_costs(trip(), search=self.search_category("accommodation", [{
            "title": "Kyoto hotel rates", "url": "https://example.test/hotel",
            "content": "Accommodation room prices are INR 4,000 to 6,000 per night.",
        }]))
        self.assertEqual(result.status, "available")
        estimate = result.estimates[0]
        self.assertEqual((estimate.amount_min, estimate.amount, estimate.currency), (4000, 6000, "INR"))
        self.assertEqual(estimate.basis, "per_room_per_night")
        self.assertEqual(estimate.source_url, "https://example.test/hotel")
        self.assertEqual(estimate.retrieved_on, date.today())
        self.assertEqual(estimate.certainty, "estimated")
        self.assertEqual(estimate.confidence_level, "low")

    def test_ambiguous_currency_and_missing_price_are_not_invented(self):
        result = research_trip_costs(trip(), search=self.search_category("food_dining", [{
            "title": "Kyoto meals", "url": "https://example.test/food",
            "content": "Meals cost about $30 per day.",
        }]))
        self.assertEqual(result.estimates, [])
        self.assertEqual(result.status, "partial")
        self.assertIn("ambiguous_currency", result.sources[0].rejection_reasons)

    def test_amount_without_cost_basis_is_not_scaled_or_allocated(self):
        result = research_trip_costs(trip(), search=self.search_category("accommodation", [{
            "title": "Kyoto hotel rates", "url": "https://example.test/hotel",
            "content": "Accommodation costs INR 5,000.",
        }]))
        self.assertEqual(result.estimates, [])
        self.assertEqual(result.status, "partial")
        self.assertIn("missing_cost_basis", result.sources[0].rejection_reasons)

    def test_snippet_with_multiple_prices_is_left_unallocated(self):
        result = research_trip_costs(trip(), search=self.search_category("accommodation", [{
            "title": "Kyoto travel cost guide", "url": "https://example.test/costs",
            "content": "Flights cost INR 40,000 per traveler and accommodation room costs INR 5,000 per room per night.",
        }]))
        self.assertEqual(len(result.estimates), 1)
        self.assertEqual(result.estimates[0].amount, 5000)
        self.assertTrue(result.price_statements)
        self.assertTrue(any(statement.accepted for statement in result.price_statements))
        self.assertTrue(any("Flights" in statement.description and not statement.accepted for statement in result.price_statements))

    def test_different_currency_is_preserved_for_allocation_to_exclude(self):
        result = research_trip_costs(trip(currency="INR"), search=self.search_category("local_transportation", [{
            "title": "Kyoto local transit", "url": "https://example.test/transit",
            "content": "Kyoto local transit fare costs JPY 900 per ride.",
        }]))
        self.assertEqual(result.estimates[0].currency, "JPY")
        self.assertEqual(result.estimates[0].basis, "per_ride")

    def test_multiple_sources_are_preserved_as_alternatives_not_summed(self):
        result = research_trip_costs(trip(), search=self.search_category("accommodation", [
            {"title": "Kyoto Hotel A", "url": "https://example.test/a", "content": "Kyoto hotel room INR 5000 per night."},
            {"title": "Kyoto Hotel B", "url": "https://example.test/b", "content": "Kyoto hotel room rate INR 8000 per room per night."},
        ]))
        accommodation = [e for e in result.estimates if e.category == "accommodation"]
        self.assertEqual(accommodation, [])
        self.assertEqual(len([s for s in result.price_statements if s.accepted]), 2)

    def test_provider_failure_is_graceful(self):
        def fail(**_):
            raise TimeoutError("provider detail must not leak")
        result = research_trip_costs(trip(), search=fail)
        self.assertEqual(result.status, "unavailable")
        self.assertNotIn("provider detail", result.note)

    def test_researched_daily_cost_scales_by_travellers_and_duration(self):
        result = research_trip_costs(trip(travelers=2, days=4), search=self.search_category("food_dining", [{
            "title": "Kyoto dining costs", "url": "https://example.test/food",
            "content": "Food and dining average INR 800 per person per day.",
        }]))
        allocation = build_budget_allocation(trip(travelers=2, days=4), result.estimates)
        self.assertEqual(allocation.amount_for("food_dining"), 6400)
        self.assertEqual(allocation.categories[2].certainty, "estimated")

    def test_jpy_food_range_preserves_source_confidence_and_scales(self):
        result = research_trip_costs(trip(currency="JPY", travelers=2, days=4), search=self.search_category("food_dining", [{
            "title": "Kyoto Food Guide 2026", "url": "https://www.japan-atlas.com/kyoto/food-guide",
            "content": "Kyoto food costs roughly 4,000-7,000 yen per person per day.",
        }]))
        estimate = result.estimates[0]
        self.assertEqual((estimate.amount_min, estimate.amount_max, estimate.currency), (4000, 7000, "JPY"))
        self.assertEqual(estimate.basis, "per_traveler_per_day")
        self.assertEqual(estimate.confidence_level, "low")
        self.assertEqual(estimate.source_url, "https://www.japan-atlas.com/kyoto/food-guide")
        allocation = build_budget_allocation(trip(currency="JPY", travelers=2, days=4), result.estimates)
        self.assertEqual(allocation.amount_for("food_dining"), 56000)
        self.assertEqual(allocation.categories[2].known_cost_estimate_min, 32000)

    def test_multiple_fares_on_one_page_are_individual_statements(self):
        result = research_trip_costs(trip(), search=self.search_category("local_transportation", [{
            "title": "Kyoto City Bus fares", "url": "https://example.test/kyoto-fares",
            "content": "Adult bus fare: JPY 230 per ride\nChild bus fare: 120 yen per ride\nOne-day adult pass: ¥1,100, valid for one day\nOne-day child pass: ¥550, valid for one day",
        }]))
        statements = result.price_statements
        self.assertEqual(len(statements), 4)
        self.assertTrue(all(statement.accepted for statement in statements))
        self.assertEqual([item.amount_max for item in statements], [230, 120, 1100, 550])
        self.assertEqual([item.currency for item in statements], ["JPY"] * 4)
        self.assertEqual([item.fare_class for item in statements], ["adult", "child", "adult", "child"])
        self.assertEqual([item.basis for item in statements], ["per_ride", "per_ride", "per_person_per_day", "per_person_per_day"])
        self.assertEqual([item.ticket_type for item in statements], [None, None, "day_pass", "day_pass"])
        self.assertEqual(result.estimates, [])
        self.assertEqual(len(result.options), 4)

    def test_jpy_currency_code_yen_word_and_yen_symbol_are_supported(self):
        result = research_trip_costs(trip(), search=self.search_category("local_transportation", [{
            "title": "Kyoto transit fares", "url": "https://example.test/jpy-fares",
            "content": "Kyoto subway fare JPY 220 per ride; Kyoto city bus fare 230 yen per ride; Kyoto day pass ¥1,100 per day.",
        }]))
        self.assertEqual([item.currency for item in result.price_statements if item.accepted], ["JPY"] * 3)
        self.assertEqual([item.amount_max for item in result.price_statements if item.accepted], [220, 230, 1100])

    def test_nearby_basis_is_specific_and_page_level_basis_is_not_reused(self):
        result = research_trip_costs(trip(), search=self.search_category("accommodation", [{
            "title": "Kyoto hotel rates per night", "url": "https://example.test/rooms",
            "content": "Budget room: JPY 8,000 per room per night\nWeekend special price: JPY 6,000",
        }]))
        first, second = result.price_statements
        self.assertTrue(first.accepted)
        self.assertEqual(first.basis, "per_room_per_night")
        self.assertFalse(second.accepted)
        self.assertIn("missing_cost_basis", second.rejection_reasons)

    def test_total_amount_does_not_inherit_previous_price_basis(self):
        result = research_trip_costs(trip(), search=self.search_category("accommodation", [{
            "title": "Kyoto ryokan rates", "url": "https://example.test/ryokan",
            "content": "Kyoto ryokan stay JPY 40,000 per person per night totals JPY 160,000 for the full stay.",
        }]))
        self.assertEqual(len(result.price_statements), 2)
        self.assertTrue(result.price_statements[0].accepted)
        self.assertEqual(result.price_statements[0].basis, "per_person_per_night")
        self.assertFalse(result.price_statements[1].accepted)
        self.assertIn("missing_cost_basis", result.price_statements[1].rejection_reasons)

    def test_kyoto_page_does_not_apply_prices_for_other_cities(self):
        result = research_trip_costs(trip(), search=self.search_category("accommodation", [{
            "title": "Japan Hotel Prices Tokyo vs Kyoto", "url": "https://example.test/japan-hotels",
            "content": "Tokyo capsule hotels run JPY 5,000 per capsule per night. Kyoto business hotel room runs JPY 9,000 per room per night.",
        }]))
        accepted = [item for item in result.price_statements if item.accepted]
        self.assertEqual(len(accepted), 1)
        self.assertEqual(accepted[0].amount_max, 9000)
        self.assertTrue(any("irrelevant_source" in item.rejection_reasons for item in result.price_statements))

    def test_meal_price_without_daily_basis_is_not_used_as_daily_food_budget(self):
        result = research_trip_costs(trip(), search=self.search_category("food_dining", [{
            "title": "Kyoto restaurant meal prices", "url": "https://example.test/meal",
            "content": "Kyoto restaurant lunch is JPY 1,200 per person.",
        }]))
        self.assertTrue(result.price_statements[0].accepted)
        self.assertEqual(result.price_statements[0].basis, "per_person")
        self.assertEqual(result.estimates, [])

    def test_accommodation_person_price_without_night_unit_is_not_scaled(self):
        result = research_trip_costs(trip(), search=self.search_category("accommodation", [{
            "title": "Kyoto ryokan rates", "url": "https://example.test/ryokan-price",
            "content": "Kyoto ryokan stay JPY 25,000 per person.",
        }]))
        self.assertFalse(any(item.accepted for item in result.price_statements))
        self.assertTrue(any("ambiguous_accommodation_unit" in item.rejection_reasons for item in result.price_statements))
        self.assertEqual(result.estimates, [])

    def test_accommodation_requires_an_explicit_room_or_guest_unit(self):
        result = research_trip_costs(trip(), search=self.search_category("accommodation", [{
            "title": "Kyoto hotel rates", "url": "https://example.test/hotel-night",
            "content": "Kyoto hotel price is JPY 12,000 per night.",
        }]))
        statement = result.price_statements[0]
        self.assertFalse(statement.accepted)
        self.assertIn("ambiguous_accommodation_unit", statement.rejection_reasons)
        self.assertEqual(result.estimates, [])

    def test_lodging_tax_example_is_not_an_accommodation_price(self):
        result = research_trip_costs(trip(), search=self.search_category("accommodation", [{
            "title": "Japan Hotels and Lodging Tax Guide", "url": "https://example.test/hotel-tax",
            "content": "Kyoto room works out at JPY 7,000 per person per night, which falls in the lodging tax band.",
        }]))
        self.assertFalse(result.price_statements[0].accepted)
        self.assertIn("illustrative_example", result.price_statements[0].rejection_reasons)
        self.assertEqual(result.estimates, [])

    def test_kyoto_accommodation_tax_amount_is_not_a_hotel_rate(self):
        result = research_trip_costs(trip(currency="JPY"), search=self.search_category("accommodation", [{
            "title": "Kyoto accommodation tax table", "url": "https://example.test/kyoto-tax",
            "content": "Kyoto accommodation tax is JPY 200 per person per night. Hotel room rates are not listed.",
        }]))
        tax = next(item for item in result.price_statements if item.amount_max == 200)
        self.assertFalse(tax.accepted)
        self.assertIn("tax_amount", tax.rejection_reasons)
        self.assertEqual(result.estimates, [])

    def test_accommodation_table_tax_row_is_diagnostic_only(self):
        result = research_trip_costs(trip(currency="JPY"), search=self.search_category("accommodation", [{
            "title": "Kyoto accommodation tax table", "url": "https://example.test/kyoto-tax-table",
            "raw_content": "One-night rate per room, taxes excluded\n|Property type|Kyoto|\n|Business hotel|¥16,000|\n|Kyoto accommodation tax|¥200|",
        }]))
        rates = [item for item in result.price_statements if item.accepted]
        tax = next(item for item in result.price_statements if item.amount_max == 200)
        self.assertEqual(len(rates), 1)
        self.assertEqual(rates[0].amount_max, 16000)
        self.assertFalse(tax.accepted)
        self.assertIn("tax_amount", tax.rejection_reasons)
        self.assertEqual(len(result.estimates), 1)

    def test_unrelated_illustrative_city_prices_are_rejected(self):
        result = research_trip_costs(trip(currency="JPY"), search=self.search_category("accommodation", [{
            "title": "Kyoto and Tokyo hotel example prices", "url": "https://example.test/examples",
            "content": "For example, a Tokyo hotel room costs JPY 9,000 per room per night.",
        }]))
        self.assertEqual(result.estimates, [])
        self.assertTrue(any("illustrative_example" in item.rejection_reasons for item in result.price_statements))
        self.assertTrue(any("irrelevant_source" in item.rejection_reasons for item in result.price_statements))

    def test_truncated_price_context_is_rejected_without_guessing_unit(self):
        result = research_trip_costs(trip(currency="JPY"), search=self.search_category("activities_attractions", [{
            "title": "Kinkaku-ji admission", "url": "https://example.test/kinkaku-truncated",
            "content": "Kinkaku-ji admission JPY 500 per",
        }]))
        self.assertEqual(result.estimates, [])
        self.assertTrue(any("missing_cost_basis" in item.rejection_reasons for item in result.price_statements))

    def test_room_person_and_capsule_nightly_units_remain_distinct(self):
        rows = [
            {"title": "Kyoto room rate", "url": "https://example.test/room", "content": "Kyoto hotel room JPY 20,000 per room per night."},
            {"title": "Kyoto capsule rate", "url": "https://example.test/capsule", "content": "Kyoto capsule hotel JPY 4,000 per capsule per night."},
            {"title": "Kyoto guest price", "url": "https://example.test/guest", "content": "Kyoto ryokan JPY 10,000 per person per night."},
        ]
        result = research_trip_costs(trip(), search=self.search_category("accommodation", rows))
        self.assertEqual({item.basis for item in result.price_statements}, {
            "per_room_per_night", "per_capsule_per_night", "per_person_per_night",
        })

    def test_distinct_ticket_options_are_not_combined(self):
        result = research_trip_costs(trip(), search=self.search_category("local_transportation", [{
            "title": "Kyoto transport tickets", "url": "https://example.test/options",
            "content": "Kyoto single ticket: JPY 230 per ride\nKyoto day pass: JPY 1,100 per day",
        }]))
        self.assertEqual(len(result.price_statements), 2)
        self.assertEqual([item.ticket_type for item in result.price_statements], ["single_ticket", "day_pass"])
        self.assertEqual(len(result.estimates), 1)
        self.assertEqual(result.estimates[0].basis, "per_traveler_per_day")

    def test_local_adult_fare_is_a_ride_not_a_person_daily_budget(self):
        result = research_trip_costs(trip(), search=self.search_category("local_transportation", [{
            "title": "Kyoto bus fare", "url": "https://example.test/kyoto-fare",
            "content": "Kyoto City Bus single ticket fare: JPY 230 per adult.",
        }]))
        statement = result.price_statements[0]
        self.assertTrue(statement.accepted)
        self.assertEqual(statement.basis, "per_ride")
        self.assertEqual(statement.ticket_type, "single_ticket")
        self.assertEqual(result.estimates, [])

    def test_general_daily_spend_for_admissions_is_not_one_admission_price(self):
        result = research_trip_costs(trip(), search=self.search_category("activities_attractions", [{
            "title": "Kyoto daily spending guide", "url": "https://example.test/daily-spend",
            "content": "Kyoto visitors may spend JPY 5,000 a day for admissions and lunches.",
        }]))
        self.assertFalse(result.price_statements[0].accepted)
        self.assertIsNone(result.price_statements[0].basis)
        self.assertIn("missing_cost_basis", result.price_statements[0].rejection_reasons)
        self.assertEqual(result.estimates, [])

    def test_generic_admission_price_is_category_evidence_not_named_activity_cost(self):
        result = research_trip_costs(trip(), search=self.search_category("activities_attractions", [{
            "title": "Kyoto attraction admission prices", "url": "https://example.test/generic-admission",
            "content": "Kyoto attraction admission is JPY 500 per admission.",
        }]))
        statement = result.price_statements[0]
        self.assertTrue(statement.accepted)
        self.assertEqual(statement.scope, "category")
        self.assertIsNone(statement.entity_name)
        self.assertEqual(result.estimates, [])

    def test_specific_attraction_admission_price_is_entity_scoped(self):
        activities = ActivityIntelligence(destination="Kyoto", activities=[ActivityCandidate(
            name="Kinkaku-ji", category="attraction", description="Golden Pavilion",
        )])
        result = research_trip_costs(trip(), activities, search=self.search_category("activities_attractions", [{
            "title": "Kinkaku-ji Official Admission Fees", "url": "https://example.test/kinkaku-fees",
            "content": "Kinkaku-ji admission fee is JPY 500 per admission.",
        }]))
        estimate = result.estimates[0]
        self.assertEqual(estimate.scope, "entity")
        self.assertEqual(estimate.entity_name, "Kinkaku-ji")
        self.assertEqual(estimate.basis, "per_admission")
        self.assertEqual(estimate.currency, "JPY")

    def test_social_post_title_cannot_assign_neighboring_prices_to_one_attraction(self):
        activities = ActivityIntelligence(destination="Kyoto", activities=[
            ActivityCandidate(name="Kinkaku-ji", category="attraction", description="Golden Pavilion"),
            ActivityCandidate(name="Ginkaku-ji", category="attraction", description="Silver Pavilion"),
        ])
        title = "Kyoto attractions price list: Kinkaku-ji JPY 500; Ginkaku-ji JPY 700; Nijo Castle JPY 1,300"
        result = research_trip_costs(trip(currency="JPY"), activities, search=self.search_category(
            "activities_attractions", [{
                "title": title,
                "url": "https://social.example.test/kyoto-prices",
                "content": (
                    "1. Golden Pavilion (Kinkaku-ji) admission fee JPY 500 per admission, open 9 AM to 5 PM\n"
                    "2. Silver Pavilion (Ginkaku-ji) admission fee JPY 700 per admission, open 9:30 AM to 5 PM"
                ),
            }],
        ))
        self.assertEqual(
            [(item.entity_name, item.amount, item.source_type) for item in result.estimates],
            [("Kinkaku-ji", 500, "third_party"), ("Ginkaku-ji", 700, "third_party")],
        )
        self.assertTrue(all(item.scope == "entity" for item in result.estimates))
        self.assertTrue(all("open" in (item.evidence_quote or "") for item in result.estimates))

    def test_long_result_title_cannot_attribute_price_without_local_attraction_name(self):
        activities = ActivityIntelligence(destination="Kyoto", activities=[ActivityCandidate(
            name="Kinkaku-ji", category="attraction", description="Golden Pavilion",
        )])
        result = research_trip_costs(trip(currency="JPY"), activities, search=self.search_category(
            "activities_attractions", [{
                "title": "Kyoto attractions: Kinkaku-ji, Ginkaku-ji, Nijo Castle prices",
                "url": "https://social.example.test/prices",
                "content": "Entry fee: ¥500 per admission.",
            }],
        ))
        self.assertEqual(result.estimates, [])
        self.assertIsNone(result.price_statements[0].entity_name)

    def test_verified_free_requires_specific_explicit_official_evidence(self):
        activities = ActivityIntelligence(destination="Kyoto", activities=[ActivityCandidate(
            name="Riverside Garden", category="park", description="Garden walk",
        )])
        official = research_trip_costs(trip(currency="JPY"), activities, search=self.search_category(
            "activities_attractions", [{
                "title": "Riverside Garden visitor information",
                "url": "https://parks.city.example.go.jp/riverside",
                "content": "Kyoto Riverside Garden admission is free.",
            }],
        ))
        third_party = research_trip_costs(trip(currency="JPY"), activities, search=self.search_category(
            "activities_attractions", [{
                "title": "Riverside Garden travel tips",
                "url": "https://travel.example.test/riverside",
                "content": "Kyoto Riverside Garden admission is free.",
            }],
        ))
        self.assertEqual(official.verified_free_activities[0].activity_name, "Riverside Garden")
        self.assertEqual(official.verified_free_activities[0].source_url, "https://parks.city.example.go.jp/riverside")
        self.assertEqual(third_party.verified_free_activities, [])

    def test_per_ride_stays_unallocated_without_ride_count(self):
        result = research_trip_costs(trip(currency="JPY"), search=self.search_category("local_transportation", [{
            "title": "Kyoto bus fare", "url": "https://example.test/fare",
            "content": "Kyoto City Bus single ride fare JPY 230 per ride.",
        }]))
        allocation = build_budget_allocation(trip(currency="JPY"), result.estimates)
        self.assertEqual(allocation.amount_for("local_transportation"), 0)
        self.assertIn("per-ride cost input", allocation.allocation_note)

    def test_day_pass_scales_per_traveller_and_trip_day(self):
        result = research_trip_costs(trip(currency="JPY", travelers=2, days=4), search=self.search_category("local_transportation", [{
            "title": "Kyoto City Bus and Subway One-Day Pass", "url": "https://example.test/day-pass",
            "content": "Kyoto City Bus and Subway One-Day Pass costs JPY 1,100 for adults per day.",
        }]))
        self.assertEqual(result.estimates, [])  # Adult fares need explicit adult-count confirmation.
        self.assertEqual(len(result.options), 1)
        selected = resolve_cost_option_selections(
            result.options, [{"option_id": result.options[0].option_id, "traveler_count": 2}],
            trip(currency="JPY", travelers=2, days=4),
        )
        allocation = build_budget_allocation(trip(currency="JPY", travelers=2, days=4), selected)
        self.assertEqual(allocation.amount_for("local_transportation"), 8800)

    def test_day_pass_duration_can_come_from_product_specific_title(self):
        result = research_trip_costs(trip(currency="JPY", travelers=2, days=4), search=self.search_category("local_transportation", [{
            "title": "Kyoto Subway & Bus 1-Day Pass Official Price", "url": "https://example.test/official-pass",
            "content": "Adult Version: JPY 1,100.",
        }]))
        statement = result.price_statements[0]
        self.assertEqual(statement.ticket_type, "day_pass")
        self.assertEqual(statement.basis, "per_person_per_day")
        self.assertEqual(result.estimates, [])
        self.assertEqual(len(result.options), 1)
        selected = resolve_cost_option_selections(
            result.options, [{"option_id": result.options[0].option_id, "traveler_count": 2}],
            trip(currency="JPY", travelers=2, days=4),
        )
        allocation = build_budget_allocation(trip(currency="JPY", travelers=2, days=4), selected)
        self.assertEqual(allocation.amount_for("local_transportation"), 8800)

    def test_two_adults_three_sightseeing_days_selects_six_adult_pass_days(self):
        request = trip(currency="JPY", travelers=2, days=3)
        result = research_trip_costs(request, search=self.search_category("local_transportation", [{
            "title": "Kyoto Subway & Bus 1-Day Pass", "url": "https://example.test/adult-pass",
            "content": "Kyoto adult pass: JPY 1,100 per adult per day.",
        }]))
        self.assertEqual(result.estimates, [])
        selected = resolve_cost_option_selections(
            result.options, [{"option_id": result.options[0].option_id, "traveler_count": 2}], request,
        )
        allocation = build_budget_allocation(request, selected)
        self.assertEqual(allocation.amount_for("local_transportation"), 6600)

    def test_subway_only_and_subway_bus_pass_products_keep_separate_options(self):
        result = research_trip_costs(trip(currency="JPY"), search=self.search_category("local_transportation", [{
            "title": "Kyoto transit pass options", "url": "https://example.test/pass-products",
            "content": "Kyoto subway-only 1-day pass: JPY 800 per adult per day\nKyoto subway-and-bus 1-day pass: JPY 1,100 per adult per day",
        }]))
        self.assertEqual(len(result.options), 2)
        self.assertNotEqual(result.options[0].group_id, result.options[1].group_id)

    def test_multi_day_pass_is_retained_without_treating_price_as_daily(self):
        result = research_trip_costs(trip(currency="JPY"), search=self.search_category("local_transportation", [{
            "title": "Kyoto Subway 2-Day Pass", "url": "https://example.test/two-day-pass",
            "content": "Adult pass price JPY 2,000.",
        }]))
        statement = result.price_statements[0]
        self.assertEqual(statement.ticket_type, "multi_day_pass")
        self.assertEqual(statement.pass_duration_days, 2)
        self.assertEqual(statement.basis, "per_person")
        self.assertEqual(result.estimates, [])

    def test_overlapping_snippet_and_page_quotes_are_not_duplicated(self):
        result = research_trip_costs(trip(), search=self.search_category("activities_attractions", [{
            "title": "Kyoto temple tickets", "url": "https://example.test/temple",
            "content": "Kyoto temple admission is JPY 500.",
            "raw_content": "Kyoto temple admission is JPY 500 and it is open daily.",
        }]))
        self.assertEqual(len(result.price_statements), 1)

    def test_unlabeled_years_and_durations_are_not_price_statements(self):
        result = research_trip_costs(trip(), search=self.search_category("activities_attractions", [{
            "title": "Kyoto Museum admission information", "url": "https://example.test/museum",
            "content": "Kyoto museum hours 9 AM to 5 PM in 2026. Visit duration is 90 minutes.",
        }]))
        self.assertEqual(result.price_statements, [])
        self.assertEqual(result.estimates, [])

    def test_local_transport_query_is_kyoto_targeted(self):
        observed = []
        def search(query, **_):
            observed.append(query)
            return [{"title": "Sacramento transit fares", "url": "https://example.test/us", "content": "US city bus fare $2 per ride."}] if "[CATEGORY:local_transportation]" in query else []
        result = research_trip_costs(trip(), search=search)
        local_query = next(query for query in observed if "[CATEGORY:local_transportation]" in query)
        self.assertIn("site:kyoto.travel", local_query)
        self.assertIn("city.kyoto.lg.jp", local_query)
        self.assertEqual(result.estimates, [])
        self.assertIn("irrelevant_source", result.price_statements[0].rejection_reasons)

    def test_duplicate_url_results_collapse_to_one_source_and_statement(self):
        row = {"title": "Kyoto dining menu", "url": "https://example.test/kyoto-menu?utm_source=one", "content": "Kyoto meal price INR 900 per person per day."}
        duplicate = {**row, "url": "https://example.test/kyoto-menu?utm_source=two"}
        result = research_trip_costs(trip(), search=self.search_category("food_dining", [row, duplicate]))
        self.assertEqual(len(result.sources), 1)
        self.assertEqual(len(result.price_statements), 1)

    def test_jpy_evidence_is_not_mixed_into_inr_budget(self):
        result = research_trip_costs(trip(currency="INR"), search=self.search_category("local_transportation", [{
            "title": "Kyoto bus fare", "url": "https://example.test/kyoto-bus",
            "content": "Kyoto bus single ticket JPY 230 per ride.",
        }]))
        self.assertTrue(result.price_statements[0].accepted)
        self.assertEqual(result.price_statements[0].currency, "JPY")
        allocation = build_budget_allocation(trip(currency="INR"), result.estimates)
        self.assertEqual(allocation.amount_for("local_transportation"), 0)
        self.assertIn("different currency", allocation.allocation_note)

    def test_transport_options_require_explicit_confirmation_and_adult_count(self):
        result = research_trip_costs(trip(currency="JPY", travelers=2, days=4), search=self.search_category("local_transportation", [{
            "title": "Kyoto Subway and Bus 1-Day Pass", "url": "https://example.test/pass",
            "content": "Adult pass: JPY 1,100 per person per day.",
        }]))
        self.assertEqual(len(result.options), 1)
        option = result.options[0]
        with self.assertRaisesRegex(ValueError, "Confirm the number of adult"):
            resolve_cost_option_selections(result.options, [{"option_id": option.option_id}], trip(currency="JPY", travelers=2, days=4))
        selected = resolve_cost_option_selections(result.options, [{"option_id": option.option_id, "traveler_count": 1}], trip(currency="JPY", travelers=2, days=4))
        allocation = build_budget_allocation(trip(currency="JPY", travelers=2, days=4), selected)
        self.assertEqual(allocation.amount_for("local_transportation"), 4400)
        self.assertEqual(resolve_cost_option_selections(result.options, [], trip(currency="JPY")), [])

    def test_multiple_transport_options_are_selectable_but_competitors_rejected(self):
        result = research_trip_costs(trip(currency="JPY"), search=self.search_category("local_transportation", [
            {"title": "Kyoto day pass", "url": "https://example.test/pass-a", "content": "Kyoto day pass JPY 1,100 per person per day."},
            {"title": "Kyoto day pass alternative", "url": "https://example.test/pass-b", "content": "Kyoto day pass JPY 1,500 per person per day."},
        ]))
        self.assertEqual(len(result.options), 2)
        with self.assertRaisesRegex(ValueError, "one competing cost option group"):
            resolve_cost_option_selections(result.options, [{"option_id": item.option_id} for item in result.options], trip(currency="JPY"))

    def test_multiday_pass_duration_does_not_become_a_one_day_pass_price(self):
        result = research_trip_costs(trip(currency="JPY"), search=self.search_category("local_transportation", [{
            "title": "Kyoto Bus Pass discussion", "url": "https://example.test/multiday-context",
            "content": "The 2-day pass at 2,000 yen is a different question.",
        }]))
        statement = next(item for item in result.price_statements if item.amount_max == 2000)
        self.assertEqual(statement.ticket_type, "multi_day_pass")
        self.assertEqual(statement.pass_duration_days, 2)
        self.assertNotEqual(statement.basis, "per_person_per_day")
        self.assertEqual(result.options, [])

    def test_per_ride_option_needs_quantity_and_scales_explicitly(self):
        result = research_trip_costs(trip(currency="JPY"), search=self.search_category("local_transportation", [{
            "title": "Kyoto single ride", "url": "https://example.test/ride", "content": "Kyoto bus fare JPY 230 per ride.",
        }]))
        option = result.options[0]
        with self.assertRaisesRegex(ValueError, "ride count"):
            resolve_cost_option_selections(result.options, [{"option_id": option.option_id}], trip(currency="JPY"))
        selected = resolve_cost_option_selections(result.options, [{"option_id": option.option_id, "quantity": 4}], trip(currency="JPY"))
        allocation = build_budget_allocation(trip(currency="JPY"), selected)
        self.assertEqual(allocation.amount_for("local_transportation"), 920)

    def test_accommodation_table_maps_kyoto_column_and_preserves_tax_status(self):
        result = research_trip_costs(trip(currency="JPY"), search=self.search_category("accommodation", [{
            "title": "Kyoto accommodation survey", "url": "https://example.test/table",
            "raw_content": "One-night rates, 2 guests per room, per room, taxes included\n|Property type|Tokyo|Kyoto|\n|Business hotel|¥20,000|¥16,000|\n|Capsule hotel|¥8,000|¥4,000|",
        }]))
        accepted = [item for item in result.price_statements if item.accepted]
        self.assertEqual(len(accepted), 1)
        self.assertEqual(accepted[0].amount_max, 16000)
        self.assertTrue(all(item.currency == "JPY" and item.taxes_included is True for item in accepted))
        self.assertEqual(accepted[0].basis, "per_room_per_night")
        self.assertTrue(any("ambiguous_accommodation_unit" in item.rejection_reasons for item in result.price_statements))
        self.assertEqual(len(result.options), 1)

    def test_table_with_explicit_capsule_basis_is_accepted(self):
        result = research_trip_costs(trip(currency="JPY"), search=self.search_category("accommodation", [{
            "title": "Kyoto capsule pricing", "url": "https://example.test/capsule-table",
            "raw_content": "One-night rate per capsule per night\n|Accommodation type|Kyoto|\n|Capsule hotel|¥4,000|",
        }]))
        statement = next(item for item in result.price_statements if item.accepted)
        self.assertEqual(statement.basis, "per_capsule_per_night")

    def test_accommodation_table_exclusion_tax_and_ambiguous_unit(self):
        result = research_trip_costs(trip(currency="JPY"), search=self.search_category("accommodation", [{
            "title": "Kyoto accommodation survey", "url": "https://example.test/tax-table",
            "raw_content": "One-night rate, taxes excluded\n|Accommodation type|Kyoto|\n|Business hotel|¥12,000|",
        }]))
        self.assertTrue(all(not item.accepted for item in result.price_statements))
        self.assertTrue(any("ambiguous_accommodation_unit" in item.rejection_reasons for item in result.price_statements))
        self.assertTrue(all(not item.accepted for item in result.price_statements))

    def test_accommodation_room_table_does_not_multiply_per_room_by_travellers(self):
        result = research_trip_costs(trip(currency="JPY", travelers=2), search=self.search_category("accommodation", [{
            "title": "Kyoto room survey", "url": "https://example.test/room-table",
            "raw_content": "One-night rate, per room, taxes excluded\n|Property type|Kyoto|\n|Business hotel|¥12,000|",
        }]))
        option = result.options[0]
        request = trip(currency="JPY", travelers=2, days=3)
        selected = resolve_cost_option_selections(result.options, [{"option_id": option.option_id}], request)
        allocation = build_budget_allocation(request, selected)
        self.assertEqual(allocation.amount_for("accommodation"), 24000)  # two room nights, not three trip days or four guest-nights

    def test_food_remains_low_confidence_and_scales_by_travellers_and_days(self):
        result = research_trip_costs(trip(currency="JPY", travelers=2, days=3), search=self.search_category("food_dining", [{
            "title": "Kyoto food guide", "url": "https://example.test/food",
            "content": "Kyoto food costs JPY 4,000-7,000 per person per day.",
        }]))
        allocation = build_budget_allocation(trip(currency="JPY", travelers=2, days=3), result.estimates)
        self.assertEqual(allocation.amount_for("food_dining"), 42000)
        self.assertEqual(allocation.categories[2].known_cost_estimate_min, 24000)
        self.assertEqual(result.estimates[0].confidence_level, "low")


if __name__ == "__main__":
    unittest.main()
