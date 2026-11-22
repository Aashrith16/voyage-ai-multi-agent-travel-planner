import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from pydantic import ValidationError

from voyage_ai import gemini_config
from voyage_ai.agents import destination_agent, request_agent
from voyage_ai.models.trip import TripRequest


class GeminiAgentConfigurationTests(unittest.TestCase):
    def test_default_and_environment_model_selection(self):
        with patch.dict("os.environ", {}, clear=True):
            self.assertEqual(gemini_config.get_gemini_model(), "gemini-3.5-flash-lite")
        with patch.dict("os.environ", {"GEMINI_MODEL": "gemini-test-model"}):
            self.assertEqual(gemini_config.get_gemini_model(), "gemini-test-model")
        with patch.dict("os.environ", {"GEMINI_MODEL": "  "}):
            self.assertEqual(gemini_config.get_gemini_model(), "gemini-3.5-flash-lite")

    def test_request_agent_uses_configured_model_and_parses_structured_output(self):
        output = {
            "origin": "Hyderabad",
            "destination": "Kyoto",
            "departure_date": "2026-11-27",
            "return_date": "2026-11-29",
            "travelers": 2,
            "budget": 180000,
            "currency": "JPY",
            "interests": ["culture"],
        }
        interaction = SimpleNamespace(output_text=json.dumps(output))
        with (
            patch.dict("os.environ", {"GEMINI_MODEL": "gemini-test-model"}),
            patch.object(request_agent.client.interactions, "create", return_value=interaction) as create,
        ):
            draft = request_agent.understand_trip_request("Plan a trip from Hyderabad to Kyoto")

        self.assertEqual(create.call_args.kwargs["model"], "gemini-test-model")
        self.assertEqual(draft.destination, "Kyoto")
        self.assertEqual(draft.currency, "JPY")
        self.assertEqual(draft.missing_fields, [])
        self.assertEqual(create.call_args.kwargs["response_format"]["mime_type"], "application/json")

    def test_request_agent_preserves_schema_validation_errors(self):
        with patch.object(
            request_agent.client.interactions,
            "create",
            return_value=SimpleNamespace(output_text='{"travelers": 0}'),
        ):
            with self.assertRaises(ValidationError):
                request_agent.understand_trip_request("Plan a trip")

    def test_destination_agent_uses_configured_model_and_validates_source_ids(self):
        source = {"id": 1, "title": "Official guide", "url": "https://example.test/kyoto", "content": "Evidence"}
        trip = TripRequest(
            origin="Hyderabad", destination="Kyoto", departure_date="2026-11-27",
            return_date="2026-11-29", travelers=2, budget=180000, currency="JPY",
        )
        output = {
            "destination": "Kyoto",
            "summary": "Evidence-based summary",
            "recommendations": [{
                "name": "Kyoto National Museum", "category": "culture",
                "why_recommended": "Relevant to the stated interest.", "source_ids": [1],
            }],
            "practical_tips": [],
        }
        with (
            patch.dict("os.environ", {"GEMINI_MODEL": "gemini-test-model"}),
            patch.object(destination_agent, "search_destination", return_value=[source]),
            patch.object(
                destination_agent.client.interactions,
                "create",
                return_value=SimpleNamespace(output_text=json.dumps(output)),
            ) as create,
        ):
            research = destination_agent.research_destination(trip)

        self.assertEqual(create.call_args.kwargs["model"], "gemini-test-model")
        self.assertEqual(research.recommendations[0].name, "Kyoto National Museum")
        self.assertEqual(research.sources[0].url, source["url"])

    def test_destination_agent_does_not_call_gemini_without_research_sources(self):
        trip = TripRequest(
            origin="Hyderabad", destination="Kyoto", departure_date="2026-11-27",
            return_date="2026-11-29", travelers=2, budget=180000,
        )
        for empty_sources in ([], None):
            with self.subTest(sources=empty_sources):
                with (
                    patch.object(destination_agent, "search_destination", return_value=empty_sources),
                    patch.object(
                        destination_agent.client.interactions,
                        "create",
                        return_value=SimpleNamespace(output_text="not-json"),
                    ) as create,
                ):
                    research = destination_agent.research_destination(trip)
            self.assertEqual(create.call_count, 0)
            self.assertEqual(research.destination, "Kyoto")
            self.assertEqual(research.recommendations, [])
            self.assertIn("incomplete", research.summary)

    def test_destination_agent_accepts_all_current_source_ids(self):
        sources = [
            {"id": index, "title": f"Source {index}", "url": f"https://example.test/{index}", "content": "Evidence."}
            for index in (1, 2, 3)
        ]
        output = {
            "destination": "Kyoto", "summary": "Evidence-based.",
            "recommendations": [{"name": "Temple", "category": "culture", "why_recommended": "Evidence", "source_ids": [1, 2, 3]}],
            "practical_tips": [],
        }
        trip = TripRequest(origin="Hyderabad", destination="Kyoto", departure_date="2026-11-27", return_date="2026-11-29", travelers=2, budget=180000)
        with (
            patch.object(destination_agent, "search_destination", return_value=sources),
            patch.object(destination_agent.client.interactions, "create", return_value=SimpleNamespace(output_text=json.dumps(output))) as create,
        ):
            research = destination_agent.research_destination(trip)
        self.assertEqual(create.call_count, 1)
        self.assertEqual(research.recommendations[0].source_ids, [1, 2, 3])
        self.assertEqual([source.url for source in research.sources], [source["url"] for source in sources])

    def test_destination_agent_retries_invalid_ids_then_preserves_only_valid_associations(self):
        source = {"id": 2, "title": "Kyoto guide", "url": "https://example.test/kyoto", "content": "Evidence about a temple."}
        first = {"destination": "Kyoto", "summary": "May be unsupported.", "recommendations": [
            {"name": "Temple A", "category": "culture", "why_recommended": "Supported", "source_ids": [2]},
            {"name": "Unknown place", "category": "other", "why_recommended": "Unsupported", "source_ids": [8]},
        ], "practical_tips": ["Potentially unsupported"]}
        second = {"destination": "Kyoto", "summary": "Still incomplete.", "recommendations": [
            {"name": "Temple A", "category": "culture", "why_recommended": "Supported", "source_ids": [2, 8]},
            {"name": "Unknown place", "category": "other", "why_recommended": "Unsupported", "source_ids": [8]},
        ], "practical_tips": ["Potentially unsupported"]}
        trip = TripRequest(origin="Hyderabad", destination="Kyoto", departure_date="2026-11-27", return_date="2026-11-29", travelers=2, budget=180000)
        with (
            patch.object(destination_agent, "search_destination", return_value=[source]),
            patch.object(destination_agent.client.interactions, "create", side_effect=[
                SimpleNamespace(output_text=json.dumps(first)), SimpleNamespace(output_text=json.dumps(second)),
            ]) as create,
        ):
            research = destination_agent.research_destination(trip)

        self.assertEqual(create.call_count, 2)
        self.assertIn("only allowed source IDs are [2]", create.call_args.kwargs["input"])
        self.assertEqual(research.destination, "Kyoto")
        self.assertEqual([(item.name, item.source_ids) for item in research.recommendations], [("Temple A", [2])])
        self.assertEqual(research.practical_tips, [])
        self.assertIn("incomplete", research.summary)
        self.assertEqual(research.sources[0].url, source["url"])

    def test_destination_agent_retries_and_drops_recommendation_with_only_id_8(self):
        source = {"id": 1, "title": "Guide", "url": "https://example.test/guide", "content": "Useful evidence."}
        output = {"destination": "Kyoto", "summary": "Unsupported summary.", "recommendations": [
            {"name": "Unverified", "category": "culture", "why_recommended": "No evidence", "source_ids": [8]},
        ], "practical_tips": ["Unsupported tip"]}
        trip = TripRequest(origin="Hyderabad", destination="Kyoto", departure_date="2026-11-27", return_date="2026-11-29", travelers=2, budget=180000)
        with (
            patch.object(destination_agent, "search_destination", return_value=[source]),
            patch.object(destination_agent.client.interactions, "create", side_effect=[
                SimpleNamespace(output_text=json.dumps(output)), SimpleNamespace(output_text=json.dumps(output)),
            ]) as create,
        ):
            research = destination_agent.research_destination(trip)
        self.assertEqual(create.call_count, 2)
        self.assertEqual(research.destination, "Kyoto")
        self.assertEqual(research.recommendations, [])
        self.assertEqual(research.practical_tips, [])
        self.assertIn("incomplete", research.summary)

    def test_destination_agent_retries_malformed_source_ids_and_falls_back_safely(self):
        source = {"id": 1, "title": "Guide", "url": "https://example.test/guide", "content": "Useful evidence."}
        malformed = {"destination": "Kyoto", "summary": "Summary", "recommendations": [
            {"name": "Place", "category": "culture", "why_recommended": "Evidence", "source_ids": ["not-an-id"]},
        ], "practical_tips": []}
        valid = {"destination": "Kyoto", "summary": "Supported.", "recommendations": [
            {"name": "Place", "category": "culture", "why_recommended": "Evidence", "source_ids": [1]},
        ], "practical_tips": []}
        trip = TripRequest(origin="Hyderabad", destination="Kyoto", departure_date="2026-11-27", return_date="2026-11-29", travelers=2, budget=180000)
        with (
            patch.object(destination_agent, "search_destination", return_value=[source]),
            patch.object(destination_agent.client.interactions, "create", side_effect=[
                SimpleNamespace(output_text=json.dumps(malformed)), SimpleNamespace(output_text=json.dumps(valid)),
            ]) as create,
        ):
            research = destination_agent.research_destination(trip)
        self.assertEqual(create.call_count, 2)
        self.assertEqual(research.recommendations[0].source_ids, [1])

        with (
            patch.object(destination_agent, "search_destination", return_value=[source]),
            patch.object(destination_agent.client.interactions, "create", side_effect=[
                SimpleNamespace(output_text=json.dumps(malformed)), SimpleNamespace(output_text=json.dumps(malformed)),
            ]),
        ):
            fallback = destination_agent.research_destination(trip)
        self.assertEqual(fallback.recommendations, [])
        self.assertIn("incomplete", fallback.summary)


if __name__ == "__main__":
    unittest.main()
