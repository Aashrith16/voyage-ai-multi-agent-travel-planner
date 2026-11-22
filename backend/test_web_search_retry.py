import unittest
import json
from unittest.mock import Mock, patch

import requests
from tavily.errors import InvalidAPIKeyError, TimeoutError as TavilyTimeoutError

from voyage_ai.tools import web_search
from voyage_ai.api import TripPlanningRequest, plan_trip
from voyage_ai.auth import AuthenticatedUser
from starlette.requests import Request


class DestinationSearchRetryTests(unittest.TestCase):
    @patch("voyage_ai.tools.web_search.time.sleep")
    @patch("voyage_ai.tools.web_search.client.search")
    def test_connection_failure_retries_once_then_recovers(self, search, sleep):
        search.side_effect = [
            requests.exceptions.ConnectionError("remote closed connection"),
            {"results": [{"title": "Kyoto source", "url": "https://example.org/kyoto", "content": "Evidence"}]},
        ]

        result = web_search.search_destination("Kyoto", ["culture"])

        self.assertEqual(result[0]["id"], 1)
        search.assert_any_call(
            query="Kyoto travel guide best places for culture",
            search_depth="basic",
            max_results=6,
            timeout=web_search.DESTINATION_SEARCH_TIMEOUT_SECONDS,
        )
        self.assertEqual(search.call_count, 2)
        sleep.assert_called_once_with(0.5)

    @patch("voyage_ai.tools.web_search.time.sleep")
    @patch("voyage_ai.tools.web_search.client.search")
    def test_sdk_timeout_retries_once_then_recovers(self, search, sleep):
        search.side_effect = [
            TavilyTimeoutError(20),
            {"results": []},
        ]

        self.assertEqual(web_search.search_destination("Kyoto", []), [])
        self.assertEqual(search.call_count, 2)
        sleep.assert_called_once_with(0.5)

    @patch("voyage_ai.tools.web_search.time.sleep")
    @patch("voyage_ai.tools.web_search.client.search")
    def test_temporary_provider_server_error_retries_once_then_recovers(self, search, sleep):
        response = Mock(status_code=503)
        server_error = requests.exceptions.HTTPError("service unavailable", response=response)
        search.side_effect = [server_error, {"results": []}]

        self.assertEqual(web_search.search_destination("Kyoto", []), [])
        self.assertEqual(search.call_count, 2)
        sleep.assert_called_once_with(0.5)

    @patch("voyage_ai.tools.web_search.time.sleep")
    @patch("voyage_ai.tools.web_search.client.search")
    def test_exhausted_connection_failure_raises_safe_provider_error(self, search, sleep):
        search.side_effect = requests.exceptions.ConnectionError("private endpoint detail")

        with self.assertRaises(web_search.DestinationResearchProviderError) as raised:
            web_search.search_destination("Kyoto", ["culture"])

        self.assertEqual(search.call_count, 2)
        sleep.assert_called_once_with(0.5)
        self.assertNotIn("private endpoint detail", str(raised.exception))

    @patch("voyage_ai.tools.web_search.time.sleep")
    @patch("voyage_ai.tools.web_search.client.search")
    def test_permanent_authentication_failure_is_not_retried(self, search, sleep):
        search.side_effect = InvalidAPIKeyError("sensitive provider details")

        with self.assertRaises(web_search.DestinationResearchProviderError) as raised:
            web_search.search_destination("Kyoto", ["culture"])

        self.assertEqual(search.call_count, 1)
        sleep.assert_not_called()
        self.assertNotIn("sensitive provider details", str(raised.exception))

    @patch("voyage_ai.api.travel_request_graph.invoke")
    def test_plan_trip_returns_safe_provider_error(self, invoke):
        invoke.side_effect = web_search.DestinationResearchProviderError(
            "Destination research provider is temporarily unavailable."
        )
        request = Request({
            "type": "http", "method": "POST", "path": "/api/plan-trip",
            "headers": [], "query_string": b"", "server": ("test", 80),
            "client": ("test", 1), "scheme": "http", "http_version": "1.1",
        })

        response = plan_trip(
            TripPlanningRequest(request="Hyderabad to Kyoto, Nov 27 to 29"),
            request,
            AuthenticatedUser(id="test-user"),
        )

        body = json.loads(response.body)
        self.assertEqual(response.status_code, 502)
        self.assertEqual(body["error"]["code"], "destination_research_unavailable")
        self.assertEqual(
            body["detail"],
            "Destination research is temporarily unavailable. Please try again shortly.",
        )


if __name__ == "__main__":
    unittest.main()
