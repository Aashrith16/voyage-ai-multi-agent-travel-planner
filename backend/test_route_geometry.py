import unittest
from unittest.mock import Mock, patch

from voyage_ai.api import RouteGeometryRequest, RoutePoint, route_geometry


class RouteGeometryTests(unittest.TestCase):
    @patch("voyage_ai.api.httpx.get")
    def test_route_response_includes_driving_mode_totals_and_ordered_legs(self, get):
        response = Mock()
        response.json.return_value = {
            "code": "Ok",
            "routes": [{
                "distance": 24000,
                "duration": 1800,
                "geometry": {"coordinates": [[135.0, 35.0], [135.1, 35.1], [135.2, 35.2]]},
                "legs": [
                    {"distance": 10000, "duration": 600},
                    {"distance": 14000, "duration": 1200},
                ],
            }],
        }
        get.return_value = response

        result = route_geometry(RouteGeometryRequest(points=[
            RoutePoint(latitude=35.0, longitude=135.0),
            RoutePoint(latitude=35.1, longitude=135.1),
            RoutePoint(latitude=35.2, longitude=135.2),
        ]), request=None, current_user=None)

        self.assertEqual(result["mode"], "driving")
        self.assertEqual(result["distance_km"], 24.0)
        self.assertEqual(result["duration_minutes"], 30.0)
        self.assertEqual(result["legs"], [
            {"distance_km": 10.0, "duration_minutes": 10.0},
            {"distance_km": 14.0, "duration_minutes": 20.0},
        ])
        self.assertIn("135.0,35.0;135.1,35.1;135.2,35.2", get.call_args.args[0])

    @patch("voyage_ai.api.httpx.get")
    def test_missing_leg_measurements_remain_unavailable(self, get):
        response = Mock()
        response.json.return_value = {
            "code": "Ok",
            "routes": [{
                "distance": 1000,
                "duration": 300,
                "geometry": {"coordinates": [[135.0, 35.0], [135.1, 35.1]]},
                "legs": [{}],
            }],
        }
        get.return_value = response

        result = route_geometry(RouteGeometryRequest(points=[
            RoutePoint(latitude=35.0, longitude=135.0),
            RoutePoint(latitude=35.1, longitude=135.1),
        ]), request=None, current_user=None)

        self.assertEqual(result["legs"], [{"distance_km": None, "duration_minutes": None}])


if __name__ == "__main__":
    unittest.main()
