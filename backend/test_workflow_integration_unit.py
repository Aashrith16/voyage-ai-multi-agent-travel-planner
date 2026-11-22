import unittest
from unittest.mock import patch
from types import SimpleNamespace

from voyage_ai.models.activity import ActivityCandidate, ActivityIntelligence
from voyage_ai.models.destination import DestinationRecommendation, DestinationResearch
from voyage_ai.models.trip import TripRequestDraft
from voyage_ai.models.weather import WeatherContext
from voyage_ai.models.routing import TravelMatrix
from voyage_ai.models.itinerary import OptimizedItinerary
from voyage_ai.models.budget import BudgetAllocation
from voyage_ai.models.cost_research import CostResearchResult, CostEvidenceOption, VerifiedFreeAdmissionEvidence
from voyage_ai.models.budget import BudgetCostEstimate
from voyage_ai.models.cost_research import CostResearchSource
from datetime import date
from voyage_ai.services.budget_service import build_budget_allocation
from voyage_ai.services.trip_request_service import finalize_trip_request
from voyage_ai.graph import workflow
from voyage_ai.services.itinerary_optimizer import optimize_itinerary
from fastapi.testclient import TestClient
from voyage_ai import api
from voyage_ai.agents import destination_agent
from langgraph.types import Command


class WorkflowIntegrationTests(unittest.TestCase):
    def authenticated_test_client(self):
        from voyage_ai.auth import AuthenticatedUser, get_current_user

        overrides = api.app.dependency_overrides
        previous = overrides.get(get_current_user)
        overrides[get_current_user] = lambda: AuthenticatedUser(
            id="00000000-0000-4000-8000-000000000001",
            email="local@voyageai.test",
        )

        def restore_override():
            if previous is None:
                overrides.pop(get_current_user, None)
            else:
                overrides[get_current_user] = previous

        self.addCleanup(restore_override)
        return TestClient(api.app)

    @staticmethod
    def register_budget_review_trip(thread_id):
        from uuid import uuid4
        from voyage_ai.auth import get_current_user
        from voyage_ai.persistence import save_trip
        from unittest.mock import patch

        with patch.dict("os.environ", {"SUPABASE_URL": "", "VOYAGEAI_ENV": "development"}, clear=False):
            user = get_current_user(None)
        save_trip(user.id, str(uuid4()), thread_id, "budget_review", {})

    def test_workflow_stage_lifecycle_logs_are_enabled(self):
        from voyage_ai.diagnostics import instrument_workflow_node

        node = instrument_workflow_node("diagnostic_test_stage", lambda state: state)
        state = {"request": "deterministic"}
        with self.assertLogs("voyage_ai.diagnostics", level="INFO") as captured:
            result = node(state)

        self.assertIs(result, state)
        messages = "\n".join(captured.output)
        self.assertIn("Workflow stage entered", messages)
        self.assertIn("stage=diagnostic_test_stage", messages)
        self.assertIn("Workflow stage completed", messages)

    def test_activity_cost_evidence_is_forwarded_from_research(self):
        trip = TripRequestDraft(
            origin="Hyderabad", destination="Kyoto", departure_date="2027-04-10",
            return_date="2027-04-12", travelers=2, budget=100000, currency="INR",
            missing_fields=[],
        )
        from voyage_ai.services.trip_request_service import finalize_trip_request
        final_trip = finalize_trip_request(trip)
        activities = ActivityIntelligence(destination="Kyoto", activities=[ActivityCandidate(
            name="Kyoto Tower", category="attraction", description="View",
            estimated_duration_minutes=60,
        )])
        estimate = BudgetCostEstimate(
            category="activities_attractions", origin="Hyderabad", destination="Kyoto",
            scope="entity", entity_name="Kyoto Tower",
            amount=900, currency="INR", basis="per_traveler", source="Kyoto Tower admission",
            source_url="https://example.test/tower", confidence=.45,
            evidence_quote="Kyoto Tower admission costs INR 900 per traveler.",
            retrieved_on=date.today(),
        )
        research = CostResearchResult(
            status="available", estimates=[estimate], sources=[CostResearchSource(
                title=estimate.source, url=estimate.source_url, retrieved_on=date.today(),
                excerpt=estimate.evidence_quote,
            )],
        )
        with patch.object(workflow, "research_trip_costs", return_value=research):
            result = workflow.cost_research_node({
                "final_trip": final_trip,
                "activity_intelligence": activities,
            })
        enriched = result["activity_intelligence"].activities[0]
        self.assertEqual(enriched.estimated_cost, 900)
        self.assertEqual(enriched.cost_status, "indicative")
        self.assertEqual(enriched.cost_source_url, estimate.source_url)
        self.assertEqual(result["budget_cost_estimates"], [])

    def test_generic_activity_estimate_is_not_forwarded_to_named_attraction(self):
        trip = TripRequestDraft(
            origin="Hyderabad", destination="Kyoto", departure_date="2027-04-10",
            return_date="2027-04-12", travelers=2, budget=100000, currency="JPY",
            missing_fields=[],
        )
        final_trip = finalize_trip_request(trip)
        activities = ActivityIntelligence(destination="Kyoto", activities=[ActivityCandidate(
            name="Kinkaku-ji", category="attraction", description="Golden Pavilion",
            estimated_duration_minutes=60,
        )])
        estimate = BudgetCostEstimate(
            category="activities_attractions", origin="Hyderabad", destination="Kyoto",
            scope="category", amount=500, currency="JPY", basis="per_admission",
            source="Kyoto admission overview", source_url="https://example.test/generic",
            evidence_quote="Admission is JPY 500 per admission.",
        )
        with patch.object(workflow, "research_trip_costs", return_value=CostResearchResult(
            status="available", estimates=[estimate],
        )):
            result = workflow.cost_research_node({
                "final_trip": final_trip,
                "activity_intelligence": activities,
            })
        activity = result["activity_intelligence"].activities[0]
        self.assertIsNone(activity.estimated_cost)
        self.assertEqual(result["budget_cost_estimates"], [])

    def test_official_attraction_free_evidence_is_attached_without_zero_price(self):
        trip = TripRequestDraft(
            origin="Hyderabad", destination="Kyoto", departure_date="2027-04-10",
            return_date="2027-04-12", travelers=2, budget=100000, currency="JPY",
            missing_fields=[],
        )
        final_trip = finalize_trip_request(trip)
        activities = ActivityIntelligence(destination="Kyoto", activities=[ActivityCandidate(
            name="Riverside Garden", category="park", description="Walk the garden",
        )])
        free = VerifiedFreeAdmissionEvidence(
            activity_name="Riverside Garden", source_url="https://city.example.go.jp/garden",
            evidence_quote="Riverside Garden admission is free.", retrieved_on=date.today(),
        )
        with patch.object(workflow, "research_trip_costs", return_value=CostResearchResult(
            status="available", verified_free_activities=[free],
        )):
            result = workflow.cost_research_node({
                "final_trip": final_trip, "activity_intelligence": activities,
            })

        attached = result["activity_intelligence"].activities[0]
        self.assertEqual(attached.admission_status, "verified_free")
        self.assertEqual(attached.cost_status, "verified_free")
        self.assertIsNone(attached.estimated_cost)
        self.assertEqual(attached.cost_source_type, "official")
        self.assertEqual(attached.cost_source_url, free.source_url)

    def test_punctuation_variant_attraction_price_matches_named_activity(self):
        draft = TripRequestDraft(
            origin="Hyderabad", destination="Kyoto", departure_date="2027-04-10",
            return_date="2027-04-12", travelers=2, budget=100000, currency="JPY",
            missing_fields=[],
        )
        final_trip = finalize_trip_request(draft)
        activities = ActivityIntelligence(destination="Kyoto", activities=[ActivityCandidate(
            name="Kinkaku-ji", category="attraction", description="Golden Pavilion",
            estimated_duration_minutes=60,
        )])
        estimate = BudgetCostEstimate(
            category="activities_attractions", origin="Hyderabad", destination="Kyoto",
            scope="entity", entity_name="Kinkakuji", amount=500, currency="JPY",
            basis="per_admission", source="Kinkakuji admission", source_url="https://example.test/kinkakuji",
        )
        with patch.object(workflow, "research_trip_costs", return_value=CostResearchResult(
            status="available", estimates=[estimate],
        )):
            result = workflow.cost_research_node({"final_trip": final_trip, "activity_intelligence": activities})
        activity = result["activity_intelligence"].activities[0]
        self.assertEqual(activity.estimated_cost, 500)
        self.assertEqual(activity.cost_source_url, estimate.source_url)

    def test_graph_memory_resumes_missing_origin_clarification(self):
        incomplete = TripRequestDraft(
            origin=None, destination="Kyoto", departure_date="2027-04-10",
            return_date="2027-04-12", travelers=2, budget=100000,
            missing_fields=["origin"],
        )
        config = {"configurable": {"thread_id": "unit-origin-clarification"}}
        with patch.object(workflow, "understand_trip_request", return_value=incomplete):
            first = workflow.travel_request_graph.invoke(
                {"user_input": "Plan Kyoto trip"}, config=config
            )
            restored_state = workflow.travel_request_graph.get_state(config)
            resumed = workflow.travel_request_graph.invoke(
                Command(resume="Hyderabad"), config=config
            )

        self.assertEqual(first["__interrupt__"][0].value["questions"], ["Where will you be traveling from?"])
        self.assertIsInstance(restored_state.values["draft"], TripRequestDraft)
        self.assertEqual(resumed["draft"].origin, "Hyderabad")
        self.assertEqual(resumed["draft"].destination, "Kyoto")

    def test_checkpoint_serializer_round_trips_pydantic_models_without_pickle(self):
        draft = TripRequestDraft(
            origin="Hyderabad", destination="Kyoto",
            departure_date="2027-04-10", return_date="2027-04-12",
            travelers=2, budget=100000, interests=["temples"],
        )

        serialized_type, serialized_value = workflow.checkpoint_serializer.dumps_typed(draft)
        restored = workflow.checkpoint_serializer.loads_typed((serialized_type, serialized_value))

        self.assertEqual(serialized_type, "msgpack")
        self.assertIsInstance(restored, TripRequestDraft)
        self.assertEqual(restored, draft)
        self.assertFalse(workflow.checkpoint_serializer.pickle_fallback)

        evidence = BudgetCostEstimate(
            category="local_transportation", origin="Hyderabad", destination="Kyoto",
            amount=1100, currency="JPY", basis="per_traveler_per_day", source="Official pass",
        )
        costs = CostResearchResult(status="available", options=[CostEvidenceOption(
            option_id="roundtrip-pass", group_id="pass", label="Adult pass", estimate=evidence,
        )])
        cost_type, cost_payload = workflow.checkpoint_serializer.dumps_typed(costs)
        restored_costs = workflow.checkpoint_serializer.loads_typed((cost_type, cost_payload))
        self.assertIsInstance(restored_costs, CostResearchResult)
        self.assertIsInstance(restored_costs.options[0], CostEvidenceOption)
        self.assertEqual(restored_costs.options[0].estimate.currency, "JPY")
        free = VerifiedFreeAdmissionEvidence(
            activity_name="Verified garden", source_url="https://city.example.go.jp/garden",
            evidence_quote="Admission is free.", retrieved_on=date.today(),
        )
        free_payload = costs.model_copy(update={"verified_free_activities": [free]})
        free_type, free_bytes = workflow.checkpoint_serializer.dumps_typed(free_payload)
        restored_free = workflow.checkpoint_serializer.loads_typed((free_type, free_bytes))
        self.assertIsInstance(restored_free.verified_free_activities[0], VerifiedFreeAdmissionEvidence)

    def test_plan_trip_api_returns_frontend_expected_response_fields(self):
        expected = {
            "status": "complete",
            "final_trip": {"destination": "Kyoto"},
            "destination_research": {"destination": "Kyoto"},
            "weather_context": {"data_mode": "unavailable"},
            "activity_intelligence": {"activities": []},
            "travel_matrix": {"locations": []},
            "optimized_itinerary": {"days": []},
        }
        with patch.object(api.travel_request_graph, "invoke", return_value=expected):
            response = self.authenticated_test_client().post(
                "/api/plan-trip",
                json={"request": "Plan a trip to Kyoto"},
            )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "complete")
        for key in expected:
            self.assertIn(key, body)

    def test_saved_live_trip_request_reaches_budget_checkpoint_with_providers_mocked(self):
        draft = TripRequestDraft(
            origin="Hyderabad, India", destination="Kyoto, Japan",
            departure_date="2026-11-27", return_date="2026-11-29",
            travelers=2, budget=180000, currency="JPY",
            interests=["sightseeing", "culture", "temples", "nature", "local food"],
            missing_fields=[],
        )
        destination = DestinationResearch(
            destination="Kyoto, Japan", summary="Mocked deterministic research",
            recommendations=[], practical_tips=[], sources=[],
        )
        activity_intelligence = ActivityIntelligence(destination="Kyoto, Japan", activities=[])
        travel_matrix = TravelMatrix(locations=[], durations_minutes=[], distances_km=[])
        request_text = (
            "Plan a trip from Hyderabad, India to Kyoto, Japan. Departure 2026-11-27; "
            "return 2026-11-29. There are 2 adults and 0 children (2 travellers). "
            "Total trip budget JPY 180000. Interests: sightseeing, culture, temples, nature, and local food."
        )
        with (
            patch.object(workflow, "understand_trip_request", return_value=draft),
            patch.object(workflow, "research_destination", return_value=destination),
            patch.object(workflow, "get_weather_context", side_effect=RuntimeError("mock weather provider failure")),
            patch.object(workflow, "build_activity_intelligence", return_value=activity_intelligence),
            patch.object(workflow, "build_travel_matrix", return_value=(activity_intelligence, travel_matrix)),
            patch.object(workflow, "research_trip_costs", return_value=CostResearchResult(status="unavailable")),
        ):
            response = self.authenticated_test_client().post("/api/plan-trip", json={"request": request_text})
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["status"], "budget_review")
        self.assertEqual(body["final_trip"]["departure_date"], "2026-11-27")
        self.assertEqual(body["final_trip"]["return_date"], "2026-11-29")
        self.assertEqual(body["final_trip"]["travelers"], 2)
        self.assertEqual(body["final_trip"]["budget"], 180000)
        self.assertEqual(body["final_trip"]["currency"], "JPY")
        self.assertEqual(body["weather_context"]["data_mode"], "unavailable")
        self.assertTrue(all(
            day["temperature_max_c"] is None
            for day in body["weather_context"]["daily_weather"]
        ))

    def test_plan_trip_returns_correlated_safe_error_and_logs_failing_node(self):
        from voyage_ai.diagnostics import correlation_id_var

        draft = TripRequestDraft(
            origin="Hyderabad, India", destination="Kyoto, Japan",
            departure_date="2026-11-27", return_date="2026-11-29",
            travelers=2, budget=180000, currency="JPY", missing_fields=[],
        )
        unavailable_weather = WeatherContext(
            destination="Kyoto, Japan", latitude=None, longitude=None,
            data_mode="unavailable", disclaimer="Mocked", daily_weather=[], risks=[], summary="Unavailable",
        )
        request_text = "Plan a trip from Hyderabad, India to Kyoto, Japan with 2 adults, 0 children, JPY 180000."
        with (
            patch.dict("os.environ", {"TAVILY_API_KEY": "unit-test-secret-value"}),
            patch.object(workflow, "understand_trip_request", return_value=draft),
            patch.object(workflow, "get_weather_context", return_value=unavailable_weather),
            patch.object(workflow, "research_destination", side_effect=RuntimeError("search failed; api_key=unit-test-secret-value")),
            self.assertLogs("voyage_ai.diagnostics", level="ERROR") as captured,
        ):
            response = self.authenticated_test_client().post("/api/plan-trip", json={"request": request_text})

        self.assertEqual(response.status_code, 500)
        body = response.json()
        correlation_id = body["error"]["correlation_id"]
        self.assertEqual(response.headers["X-Correlation-ID"], correlation_id)
        self.assertEqual(body["error"]["code"], "internal_server_error")
        self.assertEqual(body["detail"], "An unexpected error occurred while planning this trip.")
        self.assertNotIn("search failed", response.text)
        self.assertNotIn("unit-test-secret-value", "\n".join(captured.output))
        self.assertIn(correlation_id, "\n".join(captured.output))
        self.assertIn("stage=research_destination", "\n".join(captured.output))
        self.assertIn("exception_type=RuntimeError", "\n".join(captured.output))
        self.assertIn("Traceback (most recent call last)", "\n".join(captured.output))
        self.assertIsNone(correlation_id_var.get())

    def test_confirm_budget_api_validates_and_resumes_with_user_caps(self):
        self.register_budget_review_trip("budget-api-test")
        trip = TripRequestDraft(
            origin="Hyderabad", destination="Kyoto",
            departure_date="2027-04-10", return_date="2027-04-12",
            travelers=2, budget=100000, currency="INR", missing_fields=[],
        )
        from voyage_ai.services.trip_request_service import finalize_trip_request
        allocation = build_budget_allocation(finalize_trip_request(trip))
        activity_intelligence = ActivityIntelligence(destination="Kyoto", activities=[ActivityCandidate(
            name="Temple", category="temple", description="Admission", estimated_duration_minutes=60,
        )])
        snapshot = SimpleNamespace(values={
            "status": "budget_review", "budget_allocation": allocation,
            "activity_intelligence": activity_intelligence,
            "final_trip": finalize_trip_request(trip),
            "travel_matrix": TravelMatrix(locations=["Temple"], durations_minutes=[[0]], distances_km=[[0]]),
        })
        result = {"status": "complete", "optimized_itinerary": {"days": []}}
        edits = {item.category: item.allocated_amount for item in allocation.categories}
        edits["activities_attractions"] = 1500
        with (
            patch.object(api.travel_request_graph, "get_state", return_value=snapshot),
            patch.object(api.travel_request_graph, "invoke", return_value=result) as invoke,
        ):
            response = self.authenticated_test_client().post(
                "/api/confirm-budget",
                json={"thread_id": "budget-api-test", "category_allocations": edits, "activity_costs": {"Temple": 450}},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "complete")
        resume = invoke.call_args.args[0].resume
        self.assertEqual(resume["category_allocations"]["activities_attractions"], 1500)
        self.assertEqual(resume["activity_costs"]["Temple"], 450)

    def test_confirm_budget_applies_selected_option_and_preserves_checkpoint_payload(self):
        self.register_budget_review_trip("selected-pass")
        draft = TripRequestDraft(
            origin="Hyderabad", destination="Kyoto", departure_date="2027-04-10",
            return_date="2027-04-12", travelers=2, budget=100000,
            currency="JPY", missing_fields=[],
        )
        final_trip = finalize_trip_request(draft)
        estimate = BudgetCostEstimate(
            category="local_transportation", origin="Hyderabad", destination="Kyoto",
            amount=1100, currency="JPY", basis="per_traveler_per_day", source="Official pass",
            source_url="https://example.test/pass", evidence_quote="JPY 1100 per person per day",
        )
        option = CostEvidenceOption(option_id="pass-option", group_id="pass", label="Adult day pass", estimate=estimate)
        allocation = build_budget_allocation(final_trip)
        intelligence = ActivityIntelligence(destination="Kyoto", activities=[ActivityCandidate(
            name="Temple", category="temple", description="Admission", estimated_duration_minutes=60,
            estimated_cost=100, currency="JPY", cost_status="indicative", cost_basis="per_group",
        )])
        matrix = TravelMatrix(locations=["Temple"], durations_minutes=[[0]], distances_km=[[0]])
        snapshot = SimpleNamespace(values={
            "status": "budget_review", "budget_allocation": allocation,
            "final_trip": final_trip, "activity_intelligence": intelligence,
            "travel_matrix": matrix, "cost_research": CostResearchResult(status="available", options=[option]),
            "budget_cost_estimates": [],
        })
        edits = {item.category: item.allocated_amount for item in allocation.categories}
        edits["local_transportation"] = 6600
        edits["activities_attractions"] = 200
        with (
            patch.object(api.travel_request_graph, "get_state", return_value=snapshot),
            patch.object(api.travel_request_graph, "invoke", return_value={"status": "complete"}) as invoke,
        ):
            response = self.authenticated_test_client().post("/api/confirm-budget", json={
                "thread_id": "selected-pass", "category_allocations": edits,
                "cost_option_selections": [{"option_id": "pass-option"}],
            })
        self.assertEqual(response.status_code, 200, response.text)
        resume = invoke.call_args.args[0].resume
        self.assertEqual(resume["cost_option_selections"], [{"option_id": "pass-option"}])
        self.assertEqual(resume["category_allocations"]["local_transportation"], 6600)

    def test_budget_review_applies_manual_activity_price(self):
        trip = TripRequestDraft(
            origin="Hyderabad", destination="Kyoto", departure_date="2027-04-10",
            return_date="2027-04-12", travelers=2, budget=100000, currency="JPY",
            missing_fields=[],
        )
        final_trip = finalize_trip_request(trip)
        intelligence = ActivityIntelligence(destination="Kyoto", activities=[ActivityCandidate(
            name="Kinkaku-ji", category="attraction", description="Golden Pavilion",
            estimated_duration_minutes=60,
        )])
        allocation = build_budget_allocation(final_trip)
        edits = {item.category: item.allocated_amount for item in allocation.categories}
        with patch.object(workflow, "interrupt", return_value={
            "category_allocations": edits,
            "activity_costs": {"Kinkaku-ji": 500},
        }):
            result = workflow.budget_review_node({
                "final_trip": final_trip,
                "budget_allocation": allocation,
                "activity_intelligence": intelligence,
            })
        activity = result["activity_intelligence"].activities[0]
        self.assertEqual(activity.estimated_cost, 500)
        self.assertEqual(activity.currency, "JPY")
        self.assertEqual(activity.cost_status, "user_provided")
        self.assertEqual(activity.cost_evidence, "User-entered estimate")

    def test_confirm_budget_resumes_for_provisional_unknown_price_activity(self):
        self.register_budget_review_trip("unknown-price-test")
        draft = TripRequestDraft(
            origin="Hyderabad", destination="Kyoto", departure_date="2027-04-10",
            return_date="2027-04-12", travelers=2, budget=100000,
            currency="INR", missing_fields=[],
        )
        trip = finalize_trip_request(draft)
        allocation = build_budget_allocation(trip)
        edits = {item.category: item.allocated_amount for item in allocation.categories}
        edits["activities_attractions"] = 1500
        snapshot = SimpleNamespace(values={
            "status": "budget_review", "budget_allocation": allocation,
            "final_trip": trip,
            "activity_intelligence": ActivityIntelligence(destination="Kyoto", activities=[ActivityCandidate(
                name="Unpriced temple", category="temple", description="Admission unknown",
                estimated_duration_minutes=60,
            )]),
            "travel_matrix": TravelMatrix(locations=["Unpriced temple"], durations_minutes=[[0]], distances_km=[[0]]),
        })
        with (
            patch.object(api.travel_request_graph, "get_state", return_value=snapshot),
            patch.object(api.travel_request_graph, "invoke", return_value={
                "status": "complete",
                "optimized_itinerary": {"budget_status": "provisional", "provisional_activities": ["Unpriced temple"]},
            }) as invoke,
        ):
            response = self.authenticated_test_client().post(
                "/api/confirm-budget",
                json={"thread_id": "unknown-price-test", "category_allocations": edits},
            )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["status"], "complete")
        self.assertEqual(
            response.json()["optimized_itinerary"]["budget_status"],
            "provisional",
        )
        invoke.assert_called_once()

    def test_regenerate_budget_keeps_cost_research_and_activity_evidence(self):
        self.register_budget_review_trip("regen-test")
        from voyage_ai.models.cost_research import CostResearchResult
        intelligence = ActivityIntelligence(destination="Kyoto", activities=[ActivityCandidate(
            name="Temple", category="temple", description="Evidence",
        )])
        costs = CostResearchResult(status="partial", note="Some costs unavailable")
        trip = finalize_trip_request(TripRequestDraft(
            origin="Hyderabad", destination="Kyoto", departure_date="2027-04-10",
            return_date="2027-04-12", travelers=2, budget=100000, currency="INR", missing_fields=[],
        ))
        allocation = build_budget_allocation(trip)
        snapshot = SimpleNamespace(values={
            "status": "budget_review", "final_trip": trip,
            "budget_allocation": allocation, "activity_intelligence": intelligence,
            "cost_research": costs,
        })
        with patch.object(api.travel_request_graph, "get_state", return_value=snapshot):
            response = self.authenticated_test_client().post("/api/regenerate-budget", json={"thread_id": "regen-test"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["cost_research"]["note"], costs.note)
        self.assertEqual(response.json()["activity_intelligence"]["activities"][0]["name"], "Temple")

    def test_optimizer_applies_activity_budget_constraint(self):
        activities = ActivityIntelligence(
            destination="Kyoto",
            activities=[
                ActivityCandidate(name="Paid", category="museum", description="Paid stop", estimated_duration_minutes=60, estimated_cost=5000, currency="INR", preference_score=.95),
                ActivityCandidate(name="Free", category="park", description="Free stop", estimated_duration_minutes=60, currency="INR", cost_status="verified_free", admission_status="verified_free", cost_source_type="official", cost_source_url="https://city.example.go.jp/free", cost_evidence="Admission is free.", preference_score=.8),
                ActivityCandidate(name="Unpriced", category="market", description="Price not sourced", estimated_duration_minutes=60, estimated_cost=None, currency="INR", preference_score=1.0),
            ],
        )
        matrix = TravelMatrix(
            locations=["Paid", "Free", "Unpriced"],
            durations_minutes=[[0, 0, 0], [0, 0, 0], [0, 0, 0]],
            distances_km=[[0, 0, 0], [0, 0, 0], [0, 0, 0]],
        )

        result = optimize_itinerary(
            activity_intelligence=activities,
            travel_matrix=matrix,
            number_of_days=1,
            activity_budget=0,
            budget_currency="INR",
        )

        self.assertNotIn("Paid", result.selected_activities)
        self.assertIn("Unpriced", result.selected_activities)
        self.assertLessEqual(result.total_activity_cost, 0)
        self.assertIn("Free", result.selected_activities)
        self.assertIn("Unpriced", result.unpriced_activities)
        self.assertEqual(result.budget_status, "provisional")
        self.assertIn("Unpriced", result.provisional_activities)
        self.assertNotIn("Paid", result.selected_activities)

    def test_optimizer_scales_per_traveller_activity_costs(self):
        activities = ActivityIntelligence(
            destination="Kyoto",
            activities=[ActivityCandidate(
                name="Ticketed", category="museum", description="Admission",
                estimated_duration_minutes=60, estimated_cost=600, currency="INR",
                cost_status="indicative", cost_basis="per_traveler",
            )],
        )
        matrix = TravelMatrix(locations=["Ticketed"], durations_minutes=[[0]], distances_km=[[0]])
        itinerary = optimize_itinerary(
            activity_intelligence=activities, travel_matrix=matrix, number_of_days=1,
            activity_budget=1199, budget_currency="INR", travelers=2,
        )
        self.assertEqual(itinerary.selected_activities, [])
        itinerary = optimize_itinerary(
            activity_intelligence=activities, travel_matrix=matrix, number_of_days=1,
            activity_budget=1200, budget_currency="INR", travelers=2,
        )
        self.assertEqual(itinerary.total_activity_cost, 1200)

    def test_optimizer_return_day_capacity_and_route_totals_are_consistent(self):
        names = ["Temple", "Garden"]
        activities = ActivityIntelligence(destination="Kyoto", activities=[
            ActivityCandidate(
                name=name, category="culture", description="Planning stop",
                estimated_duration_minutes=60, preference_score=.9,
            )
            for name in names
        ])
        matrix = TravelMatrix(
            locations=names,
            durations_minutes=[[0, 12], [12, 0]],
            distances_km=[[0, 4], [4, 0]],
        )
        itinerary = optimize_itinerary(
            activity_intelligence=activities,
            travel_matrix=matrix,
            number_of_days=2,
            daily_minutes_by_day=[300, 0],
            day_schedule_notes=[None, "Return travel day; departure time was not provided."],
        )

        self.assertEqual(itinerary.days[1].activities, [])
        self.assertIn("departure time was not provided", itinerary.days[1].schedule_note)
        day = itinerary.days[0]
        self.assertGreaterEqual(len(day.activities), 1)
        self.assertEqual(
            day.total_activity_minutes,
            sum(activity.estimated_duration_minutes for activity in day.activities),
        )
        self.assertAlmostEqual(
            day.total_travel_minutes,
            sum(activity.travel_from_previous_minutes for activity in day.activities),
        )

    def test_optimizer_can_drop_low_priority_geographically_remote_stop(self):
        names = ["Central Temple", "Central Garden", "Remote Temple"]
        activities = ActivityIntelligence(destination="Kyoto", activities=[
            ActivityCandidate(
                name=name, category="temple", description="Suggested place",
                estimated_duration_minutes=60,
                preference_score=.9 if name != "Remote Temple" else .2,
            )
            for name in names
        ])
        matrix = TravelMatrix(
            locations=names,
            durations_minutes=[
                [0, 5, 180],
                [5, 0, 180],
                [180, 180, 0],
            ],
            distances_km=[
                [0, 1, 20],
                [1, 0, 20],
                [20, 20, 0],
            ],
        )
        itinerary = optimize_itinerary(
            activity_intelligence=activities,
            travel_matrix=matrix,
            number_of_days=1,
            daily_minutes=600,
        )

        self.assertIn("Central Temple", itinerary.selected_activities)
        self.assertIn("Central Garden", itinerary.selected_activities)
        self.assertIn("Remote Temple", itinerary.dropped_activities)

    def test_category_duration_fallback_is_explicit_and_ai_estimates_are_preserved(self):
        intelligence = ActivityIntelligence(destination="Kyoto", activities=[
            ActivityCandidate(
                name="Specific temple", category="temple", description="AI estimate",
                estimated_duration_minutes=75,
                duration_estimate_basis="activity_specific_ai_estimate",
            ),
            ActivityCandidate(name="Garden", category="garden", description="Fallback"),
        ])
        result = workflow.add_planning_durations(intelligence)
        by_name = {activity.name: activity for activity in result.activities}

        self.assertEqual(by_name["Specific temple"].estimated_duration_minutes, 75)
        self.assertEqual(by_name["Specific temple"].duration_estimate_basis, "activity_specific_ai_estimate")
        self.assertEqual(by_name["Garden"].estimated_duration_minutes, 120)
        self.assertEqual(by_name["Garden"].duration_estimate_basis, "category_fallback_estimate")

    def test_accommodation_recommendation_is_excluded_but_attraction_name_is_kept(self):
        from voyage_ai.services.activity_service import build_activity_intelligence

        trip = finalize_trip_request(TripRequestDraft(
            origin="Hyderabad", destination="Kyoto", departure_date="2027-04-10",
            return_date="2027-04-12", travelers=2, budget=100000, currency="JPY",
            missing_fields=[], interests=["culture"],
        ))
        research = DestinationResearch(
            destination="Kyoto", summary="Research", practical_tips=[], sources=[],
            recommendations=[
                DestinationRecommendation(
                    name="HOTEL THE MITSUI KYOTO", category="culture",
                    why_recommended="A hotel listing", source_ids=[1], estimated_visit_minutes=180,
                ),
                DestinationRecommendation(
                    name="Hotel Gajoen Tokyo", category="museum",
                    why_recommended="A museum and cultural attraction", source_ids=[1], estimated_visit_minutes=90,
                ),
            ],
        )

        result = build_activity_intelligence(trip, research)
        self.assertEqual([activity.name for activity in result.activities], ["Hotel Gajoen Tokyo"])
        self.assertEqual(result.excluded_accommodation_names, ["HOTEL THE MITSUI KYOTO"])

    def test_structured_resolved_lodging_type_is_removed_before_routing(self):
        from voyage_ai.services.routing_service import build_travel_matrix

        activities = ActivityIntelligence(destination="Kyoto", activities=[
            ActivityCandidate(
                name="Lodging listing", category="place", description="Resolved listing",
                latitude=35.0, longitude=135.0,
                resolved_place_category="tourism", resolved_place_type="hotel",
                estimated_duration_minutes=180,
            ),
            ActivityCandidate(
                name="Museum", category="museum", description="Attraction",
                latitude=35.1, longitude=135.1, estimated_duration_minutes=90,
            ),
            ActivityCandidate(
                name="Hotel Gajoen Tokyo", category="museum", description="Museum attraction",
                latitude=35.2, longitude=135.2, estimated_duration_minutes=90,
            ),
        ])
        with (
            patch("voyage_ai.services.routing_service.enrich_activity_intelligence", return_value=activities),
            patch("voyage_ai.services.routing_service.get_route_matrix", return_value={
                "durations": [[0, 60], [60, 0]], "distances": [[0, 1000], [1000, 0]],
            }) as route_matrix,
        ):
            routed, matrix = build_travel_matrix(activities)

        self.assertEqual(matrix.locations, ["Museum", "Hotel Gajoen Tokyo"])
        self.assertEqual([activity.name for activity in routed.activities], matrix.locations)
        self.assertEqual(routed.excluded_accommodation_names, ["Lodging listing"])
        route_matrix.assert_called_once_with([(35.1, 135.1), (35.2, 135.2)])

    def test_one_sightseeing_stop_after_lodging_filter_uses_single_point_matrix(self):
        from voyage_ai.services.routing_service import build_travel_matrix

        activities = ActivityIntelligence(destination="Kyoto", activities=[
            ActivityCandidate(
                name="Hotel listing", category="hotel", description="Stay",
                latitude=35.0, longitude=135.0, estimated_duration_minutes=180,
            ),
            ActivityCandidate(
                name="Temple", category="temple", description="Visit",
                latitude=35.1, longitude=135.1, estimated_duration_minutes=90,
            ),
        ])
        with (
            patch("voyage_ai.services.routing_service.enrich_activity_intelligence", return_value=activities),
            patch("voyage_ai.services.routing_service.get_route_matrix") as route_matrix,
        ):
            routed, matrix = build_travel_matrix(activities)

        self.assertEqual([activity.name for activity in routed.activities], ["Temple"])
        self.assertEqual(matrix.locations, ["Temple"])
        self.assertEqual(matrix.durations_minutes, [[0.0]])
        route_matrix.assert_not_called()

    def test_budgeted_optimizer_handles_only_unpriced_activities(self):
        activities = ActivityIntelligence(
            destination="Kyoto",
            activities=[ActivityCandidate(
                name="Unpriced", category="museum", description="No sourced price",
                estimated_duration_minutes=60, currency="INR",
            )],
        )
        matrix = TravelMatrix(
            locations=["Unpriced"],
            durations_minutes=[[0]],
            distances_km=[[0]],
        )
        itinerary = optimize_itinerary(
            activity_intelligence=activities,
            travel_matrix=matrix,
            number_of_days=1,
            activity_budget=500,
            budget_currency="INR",
        )

        self.assertEqual(itinerary.selected_activities, ["Unpriced"])
        self.assertEqual(itinerary.unpriced_activities, ["Unpriced"])
        self.assertEqual(itinerary.provisional_activities, ["Unpriced"])
        self.assertIsNone(itinerary.provisional_activity_cost)
        self.assertIsNone(itinerary.days[0].activities[0].estimated_cost)

    def test_three_day_optimizer_schedules_resolved_unpriced_stops_provisionally(self):
        names = [f"Resolved place {index}" for index in range(8)]
        activities = ActivityIntelligence(destination="Kyoto", activities=[
            ActivityCandidate(
                name=name, category="attraction", description="Admission not researched",
                latitude=35.0 + index * 0.001, longitude=135.0 + index * 0.001,
                estimated_duration_minutes=90, currency="JPY", preference_score=.8,
            )
            for index, name in enumerate(names)
        ])
        distances = [[0 if i == j else abs(i-j) * 2.0 for j in range(8)] for i in range(8)]
        durations = [[0 if i == j else abs(i-j) * 8.0 for j in range(8)] for i in range(8)]
        itinerary = optimize_itinerary(
            activity_intelligence=activities,
            travel_matrix=TravelMatrix(locations=names, durations_minutes=durations, distances_km=distances),
            number_of_days=3,
            activity_budget=5000,
            budget_currency="JPY",
            travelers=2,
        )

        self.assertEqual(len(itinerary.days), 3)
        self.assertTrue(all(day.activities for day in itinerary.days))
        assigned = [activity.name for day in itinerary.days for activity in day.activities]
        self.assertEqual(len(assigned), len(set(assigned)))
        self.assertGreaterEqual(len(assigned), 3)
        self.assertEqual(itinerary.total_activity_cost, 0)
        self.assertIsNone(itinerary.provisional_activity_cost)
        self.assertEqual(itinerary.budget_status, "provisional")
        self.assertTrue(all(activity.requires_price_verification for day in itinerary.days for activity in day.activities))
        self.assertTrue(all(activity.estimated_cost is None for day in itinerary.days for activity in day.activities))

    def test_verified_free_activity_requires_explicit_official_evidence(self):
        official_free = ActivityCandidate(
            name="Verified garden", category="park", description="No admission fee",
            estimated_duration_minutes=60, admission_status="verified_free",
            cost_status="verified_free", cost_source_type="official",
            cost_source_url="https://city.example.go.jp/garden", cost_evidence="Admission is free.",
        )
        unknown_zero = ActivityCandidate(
            name="Unknown zero", category="park", description="No reliable price",
            estimated_duration_minutes=60, estimated_cost=0, currency="JPY",
        )
        matrix = TravelMatrix(
            locations=[official_free.name, unknown_zero.name],
            durations_minutes=[[0, 1], [1, 0]], distances_km=[[0, .1], [.1, 0]],
        )
        itinerary = optimize_itinerary(
            ActivityIntelligence(destination="Kyoto", activities=[official_free, unknown_zero]),
            matrix, number_of_days=1, activity_budget=0, budget_currency="JPY",
        )
        self.assertIn("Verified garden", itinerary.verified_free_activities)
        self.assertIn("Unknown zero", itinerary.provisional_activities)
        self.assertEqual(itinerary.priced_activity_cost, 0)
        scheduled = {item.name: item for day in itinerary.days for item in day.activities}
        self.assertEqual(scheduled["Unknown zero"].estimated_cost, None)
        self.assertTrue(scheduled["Unknown zero"].requires_price_verification)

    def test_complete_graph_runs_with_external_services_stubbed(self):
        draft = TripRequestDraft(
            origin="Hyderabad", destination="Kyoto",
            departure_date="2027-04-10", return_date="2027-04-12",
            travelers=2, budget=100000, currency="INR",
            interests=["temples"], missing_fields=[],
        )
        research = DestinationResearch(
            destination="Kyoto", summary="Research summary",
            recommendations=[], practical_tips=[], sources=[],
        )
        activities = ActivityIntelligence(
            destination="Kyoto",
            activities=[
                ActivityCandidate(name="Temple A", category="temple", description="Indoor visit", environment="indoor", estimated_duration_minutes=90, estimated_cost=500, preference_score=.9),
                ActivityCandidate(name="Garden B", category="garden", description="Outdoor visit", environment="outdoor", estimated_duration_minutes=90, estimated_cost=0, preference_score=.8),
            ],
        )
        weather = WeatherContext(
            destination="Kyoto", latitude=None, longitude=None,
            data_mode="unavailable", disclaimer="Weather provider unavailable",
            daily_weather=[], risks=[], summary="Weather unavailable",
        )
        matrix = TravelMatrix(
            locations=["Temple A", "Garden B"],
            durations_minutes=[[0, 15], [15, 0]],
            distances_km=[[0, 1], [1, 0]],
        )

        optimizer_result = OptimizedItinerary(destination="Kyoto", activity_budget=1200)
        thread_config = {"configurable": {"thread_id": "unit-workflow-smoke"}}
        with (
            patch.object(workflow, "understand_trip_request", return_value=draft),
            patch.object(workflow, "research_destination", return_value=research),
            patch.object(workflow, "get_weather_context", return_value=weather),
            patch.object(workflow, "build_activity_intelligence", return_value=activities),
            patch.object(workflow, "build_travel_matrix", return_value=(activities, matrix)),
            patch.object(workflow, "research_trip_costs", return_value=CostResearchResult(status="unavailable")),
            patch.object(workflow, "optimize_itinerary", return_value=optimizer_result) as optimize,
        ):
            review = workflow.travel_request_graph.invoke(
                {"user_input": "Plan a trip from Hyderabad to Kyoto"},
                config=thread_config,
            )
            self.assertEqual(review["status"], "budget_review")
            restored_review = workflow.travel_request_graph.get_state(thread_config)
            self.assertIsInstance(restored_review.values["budget_allocation"], BudgetAllocation)
            allocation = review["budget_allocation"]
            amounts = {item.category: item.allocated_amount for item in allocation.categories}
            amounts["activities_attractions"] = 1200
            result = workflow.travel_request_graph.invoke(
                Command(resume={"category_allocations": amounts}),
                config=thread_config,
            )

        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["final_trip"].destination, "Kyoto")
        self.assertEqual(result["destination_research"].destination, "Kyoto")
        self.assertEqual(result["weather_context"].data_mode, "unavailable")
        self.assertEqual(len(result["activity_intelligence"].activities), 2)
        self.assertEqual(result["travel_matrix"].locations, ["Temple A", "Garden B"])
        self.assertIsNotNone(result["optimized_itinerary"])
        self.assertEqual(optimize.call_args.kwargs["activity_budget"], 1200)
        self.assertEqual(optimize.call_args.kwargs["daily_minutes_by_day"], [540, 540, 0])
        self.assertEqual(optimize.call_args.kwargs["daily_buffer_minutes_by_day"], [60, 60, 0])
        self.assertIn("arrival time was not provided", optimize.call_args.kwargs["day_schedule_notes"][0])
        self.assertIn("departure time was not provided", optimize.call_args.kwargs["day_schedule_notes"][-1])

    def test_graph_reaches_budget_review_after_destination_ids_are_safely_rejected(self):
        import json
        from uuid import uuid4

        draft = TripRequestDraft(
            origin="Hyderabad", destination="Kyoto", departure_date="2026-11-27",
            return_date="2026-11-29", travelers=2, budget=180000,
            currency="JPY", interests=["culture"], missing_fields=[],
        )
        source = {"id": 1, "title": "Kyoto guide", "url": "https://example.test/kyoto", "content": "A research excerpt."}
        invalid = {
            "destination": "Kyoto", "summary": "Unverified summary.",
            "recommendations": [{"name": "Unsupported place", "category": "culture", "why_recommended": "Unverified claim", "source_ids": [8]}],
            "practical_tips": ["Unverified tip"],
        }
        weather = WeatherContext(
            destination="Kyoto", latitude=None, longitude=None, data_mode="unavailable",
            disclaimer="Weather unavailable", daily_weather=[], risks=[], summary="Weather unavailable",
        )
        empty_activities = ActivityIntelligence(destination="Kyoto", activities=[])
        empty_matrix = TravelMatrix(locations=[], durations_minutes=[], distances_km=[])
        thread_config = {"configurable": {"thread_id": f"invalid-source-{uuid4()}"}}

        with (
            patch.object(workflow, "understand_trip_request", return_value=draft),
            patch.object(workflow, "research_destination", side_effect=destination_agent.research_destination),
            patch.object(destination_agent, "search_destination", return_value=[source]),
            patch.object(destination_agent.client.interactions, "create", side_effect=[
                SimpleNamespace(output_text=json.dumps(invalid)),
                SimpleNamespace(output_text=json.dumps(invalid)),
            ]),
            patch.object(workflow, "get_weather_context", return_value=weather),
            patch.object(workflow, "build_activity_intelligence", return_value=empty_activities),
            patch.object(workflow, "build_travel_matrix", return_value=(empty_activities, empty_matrix)),
            patch.object(workflow, "research_trip_costs", return_value=CostResearchResult(status="unavailable")),
        ):
            result = workflow.travel_request_graph.invoke(
                {"user_input": "Plan a trip from Hyderabad to Kyoto"},
                config=thread_config,
            )

        self.assertEqual(result["status"], "budget_review")
        self.assertEqual(result["destination_research"].destination, "Kyoto")
        self.assertEqual(result["destination_research"].recommendations, [])
        self.assertIn("incomplete", result["destination_research"].summary)


if __name__ == "__main__":
    unittest.main()
