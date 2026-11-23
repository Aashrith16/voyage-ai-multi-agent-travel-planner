import unittest
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient

from voyage_ai import api
from voyage_ai.models.activity import ActivityCandidate, ActivityIntelligence
from voyage_ai.models.place import ResolvedPlace
from voyage_ai.services import geospatial_service, routing_service
from voyage_ai.services.routing_service import NoResolvedActivitiesError
from voyage_ai.tools import place_search
from voyage_ai.tools.place_search import PlaceLookupError, resolve_place


class GeocodingProviderTests(unittest.TestCase):
    def setUp(self):
        place_search.clear_place_cache()
        place_search._last_nominatim_request_at = 0.0

    def tearDown(self):
        place_search.clear_place_cache()

    @staticmethod
    def response(status_code, body):
        return SimpleNamespace(status_code=status_code, json=lambda: body)

    def test_geoapify_success_is_parsed_and_cached(self):
        with (
            patch.dict("os.environ", {
                "GEOCODING_PROVIDER": "auto",
                "GEOAPIFY_API_KEY": "test-only-key",
            }, clear=True),
            patch.object(place_search.httpx, "get", return_value=self.response(200, {
                "results": [{
                    "lat": 12.9716,
                    "lon": 77.5946,
                    "formatted": "Bengaluru, India",
                    "category": "tourism.attraction",
                    "result_type": "amenity",
                    "rank": {"confidence": 0.91},
                }],
            })) as request,
        ):
            first = resolve_place("Lalbagh", "Bengaluru, India")
            second = resolve_place("Lalbagh", "Bengaluru, India")

        self.assertEqual(first.latitude, 12.9716)
        self.assertEqual(first.longitude, 77.5946)
        self.assertEqual(first.display_name, "Bengaluru, India")
        self.assertEqual(first.category, "tourism.attraction")
        self.assertEqual(second, first)
        request.assert_called_once()
        self.assertEqual(request.call_args.args[0], place_search.GEOAPIFY_SEARCH_URL)
        self.assertEqual(request.call_args.kwargs["params"]["apiKey"], "test-only-key")

    def test_geoapify_provider_error_is_safe_and_not_cached(self):
        with (
            patch.dict("os.environ", {
                "GEOCODING_PROVIDER": "geoapify",
                "GEOAPIFY_API_KEY": "test-only-key",
            }, clear=True),
            patch.object(place_search.httpx, "get", return_value=self.response(503, {})) as request,
        ):
            for _ in range(2):
                with self.assertRaises(PlaceLookupError) as caught:
                    resolve_place("Lalbagh", "Bengaluru")
                self.assertEqual(caught.exception.provider, "geoapify")
                self.assertEqual(caught.exception.status_code, 503)
                self.assertNotIn("test-only-key", str(caught.exception))
        self.assertEqual(request.call_count, 2)

    def test_geoapify_rate_limit_does_not_fall_back_to_nominatim(self):
        with (
            patch.dict("os.environ", {
                "GEOCODING_PROVIDER": "auto",
                "GEOAPIFY_API_KEY": "test-only-key",
                "GEOCODING_NOMINATIM_FALLBACK": "true",
            }, clear=True),
            patch.object(place_search.httpx, "get", return_value=self.response(429, {})) as request,
        ):
            with self.assertRaises(PlaceLookupError) as caught:
                resolve_place("Lalbagh", "Bengaluru")

        self.assertEqual(caught.exception.status_code, 429)
        request.assert_called_once()

    def test_geoapify_timeout_is_reported_without_sensitive_details(self):
        with (
            patch.dict("os.environ", {
                "GEOCODING_PROVIDER": "geoapify",
                "GEOAPIFY_API_KEY": "test-only-key",
            }, clear=True),
            patch.object(place_search.httpx, "get", side_effect=place_search.httpx.TimeoutException("request URL contains key")),
        ):
            with self.assertRaises(PlaceLookupError) as caught:
                resolve_place("Lalbagh", "Bengaluru")

        self.assertNotIn("request URL", str(caught.exception))
        self.assertNotIn("test-only-key", str(caught.exception))

    def test_configured_nominatim_fallback_runs_after_geoapify_error(self):
        nominatim_result = [{
            "lat": "12.97", "lon": "77.59", "display_name": "Lalbagh, Bengaluru",
            "category": "leisure", "type": "park",
        }]
        with (
            patch.dict("os.environ", {
                "GEOCODING_PROVIDER": "auto",
                "GEOAPIFY_API_KEY": "test-only-key",
                "GEOCODING_NOMINATIM_FALLBACK": "true",
                "NOMINATIM_USER_AGENT": "VoyageAI-test/1.0",
                "NOMINATIM_CONTACT": "test@example.invalid",
            }, clear=True),
            patch.object(place_search.time, "sleep"),
            patch.object(place_search.httpx, "get", side_effect=[
                self.response(503, {}), self.response(200, nominatim_result),
            ]) as request,
        ):
            resolved = resolve_place("Lalbagh", "Bengaluru")

        self.assertEqual(resolved.place_type, "park")
        self.assertEqual(request.call_count, 2)
        nominatim_call = request.call_args_list[1].kwargs
        self.assertEqual(nominatim_call["headers"]["User-Agent"], "VoyageAI-test/1.0")
        self.assertEqual(nominatim_call["params"]["email"], "test@example.invalid")

    def test_nominatim_629_is_not_retried_with_broader_queries(self):
        with (
            patch.dict("os.environ", {"GEOCODING_PROVIDER": "nominatim"}, clear=True),
            patch.object(place_search.time, "sleep"),
            patch.object(place_search.httpx, "get", return_value=self.response(629, {})) as request,
        ):
            with self.assertRaises(PlaceLookupError) as caught:
                resolve_place("Central Park & Museum", "Bengaluru")

        self.assertEqual(caught.exception.status_code, 629)
        request.assert_called_once()


class ActivityGeocodingFailureTests(unittest.TestCase):
    @staticmethod
    def activity(name):
        return ActivityCandidate(name=name, category="attraction", description="Suggested place", estimated_duration_minutes=60)

    def test_partial_activity_failures_keep_only_real_resolved_coordinates(self):
        good_place = ResolvedPlace(
            query="Place A, Bengaluru", name="Place A", display_name="Place A, Bengaluru",
            latitude=12.9, longitude=77.6,
        )
        intelligence = ActivityIntelligence(
            destination="Bengaluru", activities=[self.activity("Place A"), self.activity("Place B")],
        )
        with patch.object(geospatial_service, "resolve_place", side_effect=[good_place, PlaceLookupError("geoapify", status_code=404)]):
            enriched = geospatial_service.enrich_activity_intelligence(intelligence)

        self.assertEqual((enriched.activities[0].latitude, enriched.activities[0].longitude), (12.9, 77.6))
        self.assertIsNone(enriched.activities[1].latitude)
        self.assertIsNone(enriched.activities[1].longitude)

    def test_routing_uses_a_single_resolved_activity_after_partial_failures(self):
        intelligence = ActivityIntelligence(destination="Bengaluru", activities=[
            self.activity("Resolved" ).model_copy(update={"latitude": 12.9, "longitude": 77.6}),
            self.activity("Unresolved"),
        ])
        with patch.object(routing_service, "enrich_activity_intelligence", return_value=intelligence):
            enriched, matrix = routing_service.build_travel_matrix(intelligence)

        self.assertEqual([item.name for item in enriched.activities], ["Resolved"])
        self.assertEqual(matrix.locations, ["Resolved"])
        self.assertEqual(matrix.durations_minutes, [[0.0]])

    def test_total_geocoding_failure_raises_specific_error(self):
        intelligence = ActivityIntelligence(destination="Bengaluru", activities=[self.activity("Unresolved")])
        with patch.object(routing_service, "enrich_activity_intelligence", return_value=intelligence):
            with self.assertRaises(NoResolvedActivitiesError):
                routing_service.build_travel_matrix(intelligence)

    def test_plan_trip_returns_safe_structured_geocoding_error(self):
        from voyage_ai.auth import AuthenticatedUser, get_current_user

        overrides = api.app.dependency_overrides
        previous = overrides.get(get_current_user)
        overrides[get_current_user] = lambda: AuthenticatedUser(
            id="00000000-0000-4000-8000-000000000001", email="local@voyageai.test",
        )
        self.addCleanup(
            lambda: overrides.pop(get_current_user, None)
            if previous is None
            else overrides.__setitem__(get_current_user, previous)
        )

        with patch.object(api.travel_request_graph, "invoke", side_effect=NoResolvedActivitiesError()):
            response = TestClient(api.app).post(
                "/api/plan-trip", json={"request": "Plan a trip from Bengaluru to Mysuru"},
            )

        self.assertEqual(response.status_code, 503)
        body = response.json()["error"]
        self.assertEqual(body["code"], "geocoding_unavailable")
        self.assertTrue(body["correlation_id"])
        self.assertIn("could not verify locations", body["message"])
        self.assertNotIn("No resolved sightseeing", response.text)


if __name__ == "__main__":
    unittest.main()
