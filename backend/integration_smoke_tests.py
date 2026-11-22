"""Optional live-service smoke tests. Set VOYAGEAI_RUN_LIVE_TESTS=1 to run.

Run from backend with:
    .venv/Scripts/python -m unittest integration_smoke_tests -v

The full trip test is separately gated because it can make many place lookups.
It runs only when VOYAGEAI_RUN_FULL_LIVE_TRIP=1 is also set.
"""

from datetime import date, datetime, timedelta
import json
import os
from pathlib import Path
from urllib.parse import urlsplit
import unittest

from dotenv import load_dotenv
from voyage_ai.models.trip import TripRequest
from voyage_ai.services.cost_research_service import _category_queries, research_trip_costs

load_dotenv(Path(__file__).parent / ".env")


class LiveIntegrationSmokeTests(unittest.TestCase):
    def require_smoke_run(self):
        if os.getenv("VOYAGEAI_RUN_LIVE_TESTS") != "1":
            self.skipTest("Set VOYAGEAI_RUN_LIVE_TESTS=1 to enable live service calls.")

    def test_gemini_connectivity(self):
        self.require_smoke_run()
        if not os.getenv("GEMINI_API_KEY"):
            self.skipTest("GEMINI_API_KEY is not configured.")

        from google import genai

        client = genai.Client()
        try:
            result = client.models.generate_content(
                model="gemini-3.5-flash-lite",
                contents="Reply with one word: connected",
            )
        finally:
            client.close()
        self.assertTrue(result.text and result.text.strip())

    def test_tavily_destination_research(self):
        self.require_smoke_run()
        if not os.getenv("TAVILY_API_KEY"):
            self.skipTest("TAVILY_API_KEY is not configured.")

        from voyage_ai.tools.web_search import search_trip_costs

        start = date.today() + timedelta(days=30)
        trip = TripRequest(
            origin="Hyderabad, India", destination="Kyoto, Japan",
            departure_date=start, return_date=start + timedelta(days=4),
            travelers=2, budget=150000, currency="INR",
            interests=["temples", "Japanese food"],
        )
        main_queries = _category_queries(trip, None)
        live_rows: dict[str, list[dict]] = {}
        query_errors: dict[str, str] = {}
        for category, query in main_queries:
            try:
                limit = 5 if category == "local_transportation" else 3
                live_rows[query] = search_trip_costs(query=query, max_results=limit)
            except Exception as error:
                live_rows[query] = []
                query_errors[category] = type(error).__name__

        costs = research_trip_costs(trip, search=lambda *, query, **_: live_rows.get(query, []))
        main_diagnostics = []
        for source in costs.sources:
            main_diagnostics.append({
                "search_categories": source.categories or [source.category],
                "search_queries": source.queries,
                "title": source.title,
                "url": source.url,
                "snippet": source.snippet,
                "page_text_excerpt": source.page_text_excerpt,
                "page_content_successfully_retrieved": source.page_content_retrieved,
                "relevant_to_destination_and_category": source.relevant,
                "price_statements": [item.model_dump(mode="json") for item in source.price_statements],
                "source_rejection_reasons": source.rejection_reasons,
            })

        price_statements = [statement for source in costs.sources for statement in source.price_statements]
        accepted = [statement for statement in price_statements if statement.accepted]
        rejected = [statement for statement in price_statements if not statement.accepted]

        report = {
            "report_type": "live_tavily_cost_research_diagnostics",
            "retrieved_at": datetime.now().astimezone().isoformat(),
            "trip_context": {
                "origin": trip.origin,
                "destination": trip.destination,
                "departure_date": trip.departure_date.isoformat(),
                "return_date": trip.return_date.isoformat(),
                "travelers": trip.travelers,
                "currency": trip.currency,
            },
            "cost_research_status": costs.status,
            "cost_research_note": costs.note,
            "search_errors": query_errors,
            "main_search_sources": main_diagnostics,
            "source_count": len(costs.sources),
            "individual_price_statement_count": len(price_statements),
            "accepted_price_statement_count": len(accepted),
            "rejected_price_statement_count": len(rejected),
            "budget_estimate_count": len(costs.estimates),
            "accepted_estimates": [item.model_dump(mode="json") for item in costs.estimates],
            "secrets_included": False,
        }
        report_dir = Path(__file__).parent / ".local_reports"
        report_dir.mkdir(parents=True, exist_ok=True)
        report_path = report_dir / "live_tavily_cost_research.json"
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

        print(f"LIVE COST RESEARCH: {len(costs.sources)} sources; {len(price_statements)} statements; {len(accepted)} accepted; {len(rejected)} rejected; {len(costs.estimates)} budget estimates")
        print(f"DIAGNOSTIC REPORT: {report_path}")
        self.assertTrue(main_diagnostics, "No main category sources were returned; report records the empty result.")

    def test_tavily_kyoto_cost_quality(self):
        """One focused, opt-in search for lodging, attraction fees and official transit."""
        self.require_smoke_run()
        if not os.getenv("TAVILY_API_KEY"):
            self.skipTest("TAVILY_API_KEY is not configured.")

        from voyage_ai.tools.web_search import search_trip_costs

        start = date.today() + timedelta(days=45)
        trip = TripRequest(
            origin="Hyderabad, India", destination="Kyoto, Japan",
            departure_date=start, return_date=start + timedelta(days=3),
            travelers=2, budget=150000, currency="INR",
            interests=["Kinkaku-ji", "Kiyomizu-dera"],
        )
        targeted_queries = {
            "accommodation": (
                "Kyoto Japan accommodation named hotel official room rates per room per night "
                "or per person per night capsule rate taxes fees price"
            ),
            "activities_attractions": (
                'Kyoto Kinkaku-ji official admission fee entrance ticket price; '
                'Kyoto Kiyomizu-dera official admission fee entrance ticket price'
            ),
            "local_transportation": (
                "site:kyoto.travel OR site:www2.city.kyoto.lg.jp Kyoto official City Bus "
                "Subway one-day pass multi-day pass adult child fare price JPY"
            ),
            "food_dining": (
                "Kyoto Japan food dining restaurant meal cost per person per day JPY "
                "credible third-party travel budget estimate food cost Kyoto"
            ),
        }
        live_rows: dict[str, list[dict]] = {}
        query_errors: dict[str, str] = {}
        for category, query in targeted_queries.items():
            try:
                live_rows[category] = search_trip_costs(query=query, max_results=5)
            except Exception as error:
                live_rows[category] = []
                query_errors[category] = type(error).__name__

        def targeted_search(*, query: str, **_):
            marker = query.split("[CATEGORY:", 1)[1].split("]", 1)[0]
            return live_rows.get(marker, [])

        costs = research_trip_costs(trip, search=targeted_search)
        source_rows = []
        for source in costs.sources:
            host = urlsplit(source.url).netloc.casefold()
            source_rows.append({
                "title": source.title,
                "url": source.url,
                "source_type": "official Kyoto transport source" if host.endswith(("kyoto.travel", "city.kyoto.lg.jp")) else "third-party or unverified",
                "categories": source.categories,
                "snippet": source.snippet,
                "page_text_excerpt": source.page_text_excerpt,
                "page_content_retrieved": source.page_content_retrieved,
                "price_statements": [item.model_dump(mode="json") for item in source.price_statements],
            })
        all_statements = [item for source in costs.sources for item in source.price_statements]
        report = {
            "report_type": "focused_live_kyoto_cost_quality",
            "retrieved_at": datetime.now().astimezone().isoformat(),
            "destination": trip.destination,
            "currency": trip.currency,
            "live_queries": targeted_queries,
            "search_errors": query_errors,
            "source_count": len(source_rows),
            "individual_price_statement_count": len(all_statements),
            "accepted_price_statement_count": sum(item.accepted for item in all_statements),
            "rejected_price_statement_count": sum(not item.accepted for item in all_statements),
            "budget_estimate_count": len(costs.estimates),
            "sources": source_rows,
            "estimates": [item.model_dump(mode="json") for item in costs.estimates],
            "selectable_options": [item.model_dump(mode="json") for item in costs.options],
            "secrets_included": False,
        }
        report_dir = Path(__file__).parent / ".local_reports"
        report_dir.mkdir(parents=True, exist_ok=True)
        report_path = report_dir / "kyoto_cost_quality_live.json"
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(
            f"LIVE KYOTO COST QUALITY: {len(source_rows)} sources; {len(all_statements)} statements; "
            f"{report['accepted_price_statement_count']} accepted; "
            f"{report['rejected_price_statement_count']} rejected; {len(costs.estimates)} estimates"
        )
        print(f"DIAGNOSTIC REPORT: {report_path}")

    def test_open_meteo_city_geocoding(self):
        self.require_smoke_run()
        from voyage_ai.tools.weather import geocode_city

        expected = {
            "Kyoto, Japan": (34.8, 35.3, 135.5, 136.0),
            "Jaipur, India": (26.7, 27.1, 75.5, 76.0),
            "Hyderabad, India": (17.1, 17.7, 78.2, 78.8),
        }
        for query, (min_lat, max_lat, min_lon, max_lon) in expected.items():
            with self.subTest(destination=query):
                place = geocode_city(query)
                self.assertEqual(place["name"].casefold(), query.split(",", 1)[0].casefold())
                self.assertTrue(min_lat <= place["latitude"] <= max_lat)
                self.assertTrue(min_lon <= place["longitude"] <= max_lon)

    def test_open_meteo_weather_retrieval(self):
        self.require_smoke_run()
        from voyage_ai.services.weather_service import get_weather_context

        start = date.today() + timedelta(days=1)
        context = get_weather_context("Kyoto, Japan", start, start + timedelta(days=1))
        self.assertNotEqual(context.data_mode, "unavailable", context.summary)
        self.assertEqual(context.destination, "Kyoto, Japan")
        self.assertTrue(context.latitude and context.longitude)
        self.assertEqual(len(context.daily_weather), 2)

    def test_osrm_routing_service(self):
        self.require_smoke_run()
        from voyage_ai.tools.weather import geocode_city
        from voyage_ai.tools.routing import get_route_matrix

        hyderabad = geocode_city("Hyderabad, India")
        jaipur = geocode_city("Jaipur, India")
        matrix = get_route_matrix([
            (hyderabad["latitude"], hyderabad["longitude"]),
            (jaipur["latitude"], jaipur["longitude"]),
        ])
        self.assertEqual(matrix.get("code"), "Ok")
        self.assertEqual(len(matrix.get("durations", [])), 2)
        self.assertEqual(len(matrix["durations"][0]), 2)

    def test_complete_trip_planning_api(self):
        self.require_smoke_run()
        if os.getenv("VOYAGEAI_RUN_FULL_LIVE_TRIP") != "1":
            self.skipTest(
                "Full trip planning is separately gated because it can trigger many place geocoding calls. "
                "Set VOYAGEAI_RUN_FULL_LIVE_TRIP=1 as well to run one live trip."
            )
        if not os.getenv("GEMINI_API_KEY"):
            self.skipTest("GEMINI_API_KEY is not configured.")
        if not os.getenv("TAVILY_API_KEY"):
            self.skipTest("TAVILY_API_KEY is not configured.")

        from fastapi.testclient import TestClient
        from voyage_ai.api import app

        client = TestClient(app)
        review_response = client.post(
            "/api/plan-trip",
            json={
                "request": (
                    "Plan a trip from Hyderabad to Kyoto, Japan from "
                    "2027-04-10 to 2027-04-12 for 2 travelers with a total "
                    "budget of 150000 INR. I enjoy temples and Japanese food."
                )
            },
        )
        self.assertEqual(review_response.status_code, 200, f"Planning API returned HTTP {review_response.status_code}.")
        review = review_response.json()
        self.assertEqual(review.get("status"), "budget_review")
        self.assertEqual(review.get("final_trip", {}).get("origin", "").casefold(), "hyderabad")
        self.assertIn("kyoto", review.get("final_trip", {}).get("destination", "").casefold())
        self.assertEqual(review.get("final_trip", {}).get("travelers"), 2)
        cost_research = review.get("cost_research") or {}
        for estimate in cost_research.get("estimates", []):
            self.assertTrue(estimate.get("source_url"))
            self.assertTrue(estimate.get("currency"))
            self.assertTrue(estimate.get("basis"))
            self.assertTrue(estimate.get("retrieved_on"))
            self.assertTrue(estimate.get("confidence_level"))
        allocation = review.get("budget_allocation") or {}
        category_allocations = {
            item["category"]: item["allocated_amount"]
            for item in allocation.get("categories", [])
        }
        food_capacity = allocation["total_budget"] - sum(
            value for key, value in category_allocations.items() if key != "food_dining"
        )
        original_food = category_allocations["food_dining"]
        if food_capacity > original_food:
            manual_food = min(original_food + 500, food_capacity)
        else:
            manual_food = max(0, original_food - 500)
        edited_category = "food_dining"
        edited_amount = manual_food
        if manual_food == original_food:
            original_reserve = category_allocations["contingency"]
            category_allocations["contingency"] = max(0, original_reserve - 500)
            self.assertNotEqual(category_allocations["contingency"], original_reserve)
            edited_category = "contingency"
            edited_amount = category_allocations["contingency"]
        else:
            category_allocations["food_dining"] = manual_food
        approved_activity_cap = category_allocations["activities_attractions"]
        response = client.post(
            "/api/confirm-budget",
            json={
                "thread_id": review.get("thread_id"),
                "category_allocations": category_allocations,
            },
        )
        self.assertEqual(response.status_code, 200, f"Budget confirmation returned HTTP {response.status_code}.")
        result = response.json()
        self.assertEqual(result.get("status"), "complete")
        self.assertIn("kyoto", result.get("final_trip", {}).get("destination", "").casefold())
        self.assertTrue(result.get("destination_research"))
        self.assertTrue(result.get("weather_context"))
        self.assertTrue(result.get("activity_intelligence"))
        self.assertTrue(result.get("travel_matrix"))
        self.assertTrue(result.get("optimized_itinerary"))
        approved = result.get("budget_allocation") or {}
        approved_categories = {
            item["category"]: item["allocated_amount"]
            for item in approved.get("categories", [])
        }
        self.assertAlmostEqual(approved_categories[edited_category], edited_amount)
        self.assertLessEqual(sum(approved_categories.values()), approved["total_budget"] + 0.01)
        itinerary = result["optimized_itinerary"]
        self.assertAlmostEqual(itinerary["activity_budget"], approved_activity_cap)
        self.assertLessEqual(itinerary["total_activity_cost"], approved_activity_cap + 0.01)
        self.assertEqual(result["final_trip"]["travelers"], 2)
        self.assertEqual(result["final_trip"]["origin"].casefold(), "hyderabad")
        self.assertEqual(result["final_trip"]["destination"], review["final_trip"]["destination"])
        self.assertNotEqual(result["weather_context"].get("data_mode"), "unavailable")
        self.assertTrue(
            all(estimate.get("certainty") == "estimated" for estimate in cost_research.get("estimates", [])),
            "Search-derived costs must remain indicative estimates.",
        )
        budget_currency = approved["currency"]
        for category in approved.get("categories", []):
            if not any(
                evidence.get("currency") == budget_currency
                for evidence in category.get("cost_evidence", [])
            ):
                self.assertIsNone(category.get("known_cost_estimate"))
        activity_by_name = {
            activity["name"]: activity
            for activity in result["activity_intelligence"].get("activities", [])
        }
        scheduled_names = [
            activity["name"]
            for day in itinerary.get("days", [])
            for activity in day.get("activities", [])
        ]
        for name in scheduled_names:
            activity = activity_by_name[name]
            self.assertIsNotNone(activity.get("estimated_cost"), f"Unknown-cost activity was scheduled: {name}")
            self.assertEqual(activity.get("currency", "").upper(), budget_currency.upper())
        print(
            f"LIVE TRIP: {result['final_trip']['origin']} to {result['final_trip']['destination']}; "
            f"travelers={result['final_trip']['travelers']}; "
            f"manual {edited_category} cap={edited_amount} {approved['currency']}; "
            f"activity cap={approved_activity_cap} {approved['currency']}; "
            f"activity estimate total={itinerary['total_activity_cost']} {approved['currency']}"
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
