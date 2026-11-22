import unittest
from unittest.mock import Mock, patch
from datetime import date

import httpx

from voyage_ai.tools import weather
from voyage_ai.services import weather_service
from voyage_ai.models.trip import TripRequestDraft
from voyage_ai.services.trip_request_service import merge_trip_drafts


class WeatherToolTests(unittest.TestCase):
    def setUp(self):
        weather._response_cache.clear()
        weather.geocode_city.cache_clear()

    @patch("voyage_ai.tools.weather.httpx.get")
    def test_geocoder_selects_exact_city_and_caches_response(self, get):
        response = Mock()
        response.status_code = 200
        response.json.return_value = {
            "results": [
                {"name": "Tokyo", "latitude": 35.68, "longitude": 139.75},
                {"name": "Kyoto", "latitude": 35.01, "longitude": 135.76, "country": "Japan"},
            ]
        }
        get.return_value = response

        result = weather.geocode_city("Kyoto")
        weather.geocode_city("Kyoto")

        self.assertEqual(result["name"], "Kyoto")
        self.assertEqual(result["latitude"], 35.01)
        get.assert_called_once()

    @patch("voyage_ai.tools.weather.httpx.get")
    def test_destination_coordinates_are_forwarded_to_forecast(self, get):
        response = Mock()
        response.status_code = 200
        response.json.return_value = {"daily": {}}
        get.return_value = response

        weather.get_forecast(35.02107, 135.75385, date(2026, 11, 20), date(2026, 11, 21))

        params = get.call_args.kwargs["params"]
        self.assertEqual(params["latitude"], 35.02107)
        self.assertEqual(params["longitude"], 135.75385)

    def test_followup_updates_preserve_other_trip_fields(self):
        trip = TripRequestDraft(
            origin="Hyderabad", destination="Kyoto",
            departure_date="2027-04-10", return_date="2027-04-17",
            travelers=2, budget=180000, currency="INR",
            interests=["food", "temples"],
        )
        date_change = merge_trip_drafts(trip, TripRequestDraft(departure_date="2027-04-12"))
        destination_change = merge_trip_drafts(date_change, TripRequestDraft(destination="Jaipur"))
        traveler_change = merge_trip_drafts(destination_change, TripRequestDraft(travelers=3))

        self.assertEqual(traveler_change.origin, "Hyderabad")
        self.assertEqual(traveler_change.destination, "Jaipur")
        self.assertEqual(traveler_change.departure_date, date(2027, 4, 12))
        self.assertEqual(traveler_change.return_date, date(2027, 4, 17))
        self.assertEqual(traveler_change.travelers, 3)
        self.assertEqual(traveler_change.budget, 180000)
        self.assertEqual(traveler_change.interests, ["food", "temples"])

    @patch("voyage_ai.tools.weather.time.sleep")
    @patch("voyage_ai.tools.weather.httpx.get")
    def test_429_respects_retry_after_and_then_succeeds(self, get, sleep):
        limited = httpx.Response(429, headers={"Retry-After": "2"}, request=httpx.Request("GET", weather.FORECAST_URL))
        success = Mock()
        success.status_code = 200
        success.json.return_value = {"daily": {}}
        get.side_effect = [limited, success]

        result = weather._get_json(weather.FORECAST_URL, {"latitude": 35.0})

        self.assertEqual(result, {"daily": {}})
        sleep.assert_called_once_with(2.0)
        self.assertEqual(get.call_count, 2)

    @patch("voyage_ai.tools.weather.httpx.get")
    def test_successful_forecast_builds_weather_context(self, get):
        response = Mock()
        response.status_code = 200
        response.json.return_value = {"daily": {
            "time": ["2026-11-21"],
            "temperature_2m_max": [12.0],
            "temperature_2m_min": [4.0],
            "precipitation_sum": [0.0],
            "precipitation_probability_max": [10],
            "weather_code": [1],
        }}
        get.return_value = response

        class FrozenDate(date):
            @classmethod
            def today(cls):
                return cls(2026, 11, 20)

        with (
            patch.object(weather_service, "date", FrozenDate),
            patch.object(weather_service, "geocode_city", return_value={
                "latitude": 35.0, "longitude": 135.0,
            }),
        ):
            context = weather_service.get_weather_context(
                "Kyoto, Japan", date(2026, 11, 21), date(2026, 11, 21),
            )

        self.assertEqual(context.data_mode, "forecast")
        self.assertEqual(context.latitude, 35.0)
        self.assertEqual(context.daily_weather[0].temperature_max_c, 12.0)

    @patch("voyage_ai.tools.weather.time.sleep")
    @patch("voyage_ai.tools.weather.httpx.get")
    def test_timeout_retries_once_and_successful_result_is_cached(self, get, sleep):
        success = Mock()
        success.status_code = 200
        success.json.return_value = {"daily": {"time": []}}
        get.side_effect = [httpx.ReadTimeout("timed out"), success]

        params = {"latitude": 35.0, "date": "timeout-cache-regression"}
        first = weather._get_json(weather.FORECAST_URL, params)
        second = weather._get_json(weather.FORECAST_URL, params)

        self.assertEqual(first, {"daily": {"time": []}})
        self.assertEqual(second, first)
        self.assertEqual(get.call_count, 2)
        sleep.assert_called_once_with(0.5)

    @patch("voyage_ai.tools.weather.time.sleep")
    @patch("voyage_ai.tools.weather.httpx.get")
    def test_temporary_503_retries_with_bounded_backoff(self, get, sleep):
        unavailable = httpx.Response(
            503, request=httpx.Request("GET", weather.FORECAST_URL),
        )
        success = Mock()
        success.status_code = 200
        success.json.return_value = {"daily": {}}
        get.side_effect = [unavailable, success]

        result = weather._get_json(weather.FORECAST_URL, {"service": "503-regression"})

        self.assertEqual(result, {"daily": {}})
        self.assertEqual(get.call_count, 2)
        sleep.assert_called_once_with(0.5)

    @patch("voyage_ai.tools.weather.time.sleep")
    @patch("voyage_ai.tools.weather.httpx.get")
    def test_429_retry_after_beyond_wait_limit_is_not_retried_early(self, get, sleep):
        limited = httpx.Response(
            429, headers={"Retry-After": "45"},
            request=httpx.Request("GET", weather.FORECAST_URL),
        )
        get.return_value = limited

        with self.assertRaises(httpx.HTTPStatusError):
            weather._get_json(weather.FORECAST_URL, {"retry-after": "long"})

        get.assert_called_once()
        sleep.assert_not_called()

    @patch("voyage_ai.tools.weather.time.sleep")
    @patch("voyage_ai.tools.weather.httpx.get")
    def test_exhausted_429_returns_explicit_unavailable_weather(self, get, sleep):
        limited = httpx.Response(
            429, request=httpx.Request("GET", weather.FORECAST_URL),
        )
        get.return_value = limited
        start = date.today().fromordinal(date.today().toordinal() + 1)
        end = date.today().fromordinal(date.today().toordinal() + 2)

        with patch.object(weather_service, "geocode_city", return_value={
            "latitude": 35.0, "longitude": 135.0,
        }):
            context = weather_service.get_weather_context("Kyoto", start, end)

        self.assertEqual(context.data_mode, "unavailable")
        self.assertTrue(all(day.temperature_max_c is None for day in context.daily_weather))
        self.assertTrue(all(risk.outdoor_suitability == "unknown" for risk in context.risks))
        self.assertEqual(get.call_count, weather._MAX_RETRY_ATTEMPTS)
        self.assertEqual(sleep.call_count, weather._MAX_RETRY_ATTEMPTS - 1)

    @patch("voyage_ai.services.weather_service.geocode_city", side_effect=RuntimeError("provider offline"))
    def test_geocoding_failure_returns_explicit_unavailable_weather(self, _geocode):
        from datetime import date

        context = weather_service.get_weather_context(
            "Kyoto", date(2027, 5, 1), date(2027, 5, 2)
        )

        self.assertEqual(context.data_mode, "unavailable")
        self.assertEqual(len(context.daily_weather), 2)
        self.assertTrue(all(day.temperature_max_c is None for day in context.daily_weather))
        self.assertTrue(all(risk.outdoor_suitability == "unknown" for risk in context.risks))


if __name__ == "__main__":
    unittest.main()
