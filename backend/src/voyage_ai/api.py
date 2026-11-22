from uuid import UUID, uuid4
from math import isfinite
import httpx

from langgraph.types import Command

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from voyage_ai.graph.workflow import (
    travel_request_graph,
)
from voyage_ai.auth import AuthenticatedUser, get_current_user
from voyage_ai.persistence import get_trip, get_trip_by_thread, list_trips, save_trip
from voyage_ai.services.budget_service import (
    apply_budget_edits,
    build_budget_allocation,
)
from voyage_ai.tools.web_search import DestinationResearchProviderError
from voyage_ai.services.cost_research_service import resolve_cost_option_selections
from voyage_ai.diagnostics import (
    correlation_id_var,
    log_unexpected_exception,
    new_correlation_id,
    safe_error_payload,
    workflow_stage_var,
)


# ==================================================
# FASTAPI APPLICATION
# ==================================================

app = FastAPI(
    title="VoyageAI API",
    description=(
        "Multi-agent AI travel planning API "
        "with research, weather intelligence, "
        "routing and OR-Tools optimization."
    ),
    version="0.1.0",
)


@app.middleware("http")
async def add_correlation_id(request: Request, call_next):
    correlation_id = new_correlation_id()
    correlation_token = correlation_id_var.set(correlation_id)
    stage_token = workflow_stage_var.set(None)
    try:
        response = await call_next(request)
    except Exception as error:
        log_unexpected_exception(
            error,
            stage=workflow_stage_var.get() or "request_middleware",
            method=request.method,
            path=request.url.path,
        )
        response = JSONResponse(
            status_code=500,
            content={
                "detail": safe_error_payload(correlation_id)["message"],
                "error": safe_error_payload(correlation_id),
            },
        )
    finally:
        workflow_stage_var.reset(stage_token)
        correlation_id_var.reset(correlation_token)
    response.headers["X-Correlation-ID"] = correlation_id
    return response


def _logged_error_response(
    request: Request,
    error: BaseException,
    *,
    stage: str,
    status_code: int = 500,
    message: str = "An unexpected error occurred while planning this trip.",
    error_code: str = "internal_server_error",
) -> JSONResponse:
    correlation_id = log_unexpected_exception(
        error,
        stage=getattr(error, "voyageai_workflow_stage", None)
        or workflow_stage_var.get()
        or stage,
        method=request.method,
        path=request.url.path,
    )
    payload = safe_error_payload(correlation_id)
    payload["code"] = error_code
    payload["message"] = message
    return JSONResponse(
        status_code=status_code,
        content={"detail": payload["message"], "error": payload},
        headers={"X-Correlation-ID": correlation_id},
    )


# ==================================================
# DEVELOPMENT CORS
# ==================================================

app.add_middleware(
    CORSMiddleware,

    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",

        "http://localhost:5173",
        "http://127.0.0.1:5173",

        "http://localhost:5174",
        "http://127.0.0.1:5174",

        "https://voyageai-pied.vercel.app",
    ],

    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==================================================
# REQUEST MODEL
# ==================================================

class TripPlanningRequest(BaseModel):

    request: str = Field(
        min_length=5,
        description=(
            "Natural-language travel request."
        ),
    )

    thread_id: str | None = Field(
        default=None,
        description=(
            "Optional conversation thread ID."
        ),
    )

class RoutePoint(BaseModel):
    latitude: float
    longitude: float


class RouteGeometryRequest(BaseModel):
    points: list[RoutePoint]


# ==================================================
# HEALTH CHECK
# ==================================================

@app.get("/")
def root():

    return {
        "name": "VoyageAI",
        "status": "running",
    }


@app.get("/api/health")
def health():

    return {
        "status": "healthy",
        "service": "VoyageAI API",
    }


@app.get("/api/trips")
def owned_trips(current_user: AuthenticatedUser = Depends(get_current_user)):
    return {"trips": list_trips(current_user.id)}


@app.get("/api/trips/{trip_id}")
def owned_trip(
    trip_id: UUID,
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    return get_trip(current_user.id, str(trip_id))

@app.post("/api/route-geometry")
def route_geometry(
    payload: RouteGeometryRequest,
    request: Request,
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Return a real drivable OSRM route
    through the supplied coordinates.
    """

    if len(payload.points) < 2:
        return {
            "geometry": [],
            "distance_km": 0,
            "duration_minutes": 0,
        }


    coordinates = ";".join(
        f"{point.longitude},{point.latitude}"
        for point in payload.points
    )


    url = (
        "https://router.project-osrm.org/"
        f"route/v1/driving/{coordinates}"
    )


    try:
        response = httpx.get(
            url,
            params={
                "overview": "full",
                "geometries": "geojson",
                "steps": "false",
            },
            timeout=30,
        )

        response.raise_for_status()

        data = response.json()


        if (
            data.get("code") != "Ok"
            or not data.get("routes")
        ):
            raise ValueError(
                "OSRM could not calculate route."
            )


        route = data["routes"][0]

        coordinates = (
            route["geometry"]["coordinates"]
        )


        # GeoJSON gives [longitude, latitude].
        # Leaflet requires [latitude, longitude].
        leaflet_geometry = [
            [latitude, longitude]
            for longitude, latitude
            in coordinates
        ]


        return {
            "geometry":
                leaflet_geometry,

            "mode": "driving",

            "distance_km":
                round(
                    route["distance"]
                    / 1000,
                    2,
                ),

            "duration_minutes":
                round(
                    route["duration"]
                    / 60,
                    1,
                ),

            "legs": [
                {
                    "distance_km": (
                        round(leg["distance"] / 1000, 2)
                        if isinstance(leg, dict) and isinstance(leg.get("distance"), (int, float))
                        else None
                    ),
                    "duration_minutes": (
                        round(leg["duration"] / 60, 1)
                        if isinstance(leg, dict) and isinstance(leg.get("duration"), (int, float))
                        else None
                    ),
                }
                for leg in route.get("legs", [])
            ],
        }


    except Exception as error:
        return _logged_error_response(
            request,
            error,
            stage="route_geometry",
            status_code=502,
            message="Could not retrieve an OSRM route.",
        )

# ==================================================
# TRIP PLANNING ENDPOINT
# ==================================================

@app.post("/api/plan-trip")
def plan_trip(
    payload: TripPlanningRequest,
    request: Request,
    current_user: AuthenticatedUser = Depends(get_current_user),
):

    existing_trip = get_trip_by_thread(current_user.id, payload.thread_id) if payload.thread_id else None
    thread_id = payload.thread_id or str(uuid4())
    trip_id = existing_trip["trip_id"] if existing_trip else str(uuid4())


    config = {
        "configurable": {
            "thread_id": thread_id,
            "trip_id": trip_id,
        }
    }


    try:

        result = (
            travel_request_graph.invoke(
                {
                    "user_input":
                        payload.request,
                },

                config=config,
            )
        )

        interrupts = result.get("__interrupt__", [])
        clarification = None
        if interrupts:
            clarification = interrupts[0].value


        response = {
            "thread_id": thread_id,

            "status": result.get(
                "status"
            ),

            "clarification": clarification,

            "clarification_questions":
                result.get(
                    "clarification_questions",
                    [],
                ),

            "final_trip":
                result.get(
                    "final_trip"
                ),

            "destination_research":
                result.get(
                    "destination_research"
                ),

            "weather_context":
                result.get(
                    "weather_context"
                ),

            "activity_intelligence":
                result.get(
                    "activity_intelligence"
                ),

            "travel_matrix":
                result.get(
                    "travel_matrix"
                ),

            "optimized_itinerary":
                result.get(
                    "optimized_itinerary"
                ),

            "budget_allocation": result.get("budget_allocation"),
            "cost_research": result.get("cost_research"),
        }


        encoded = jsonable_encoder(response)
        saved = save_trip(current_user.id, trip_id, thread_id, str(result.get("status") or "processing"), encoded)
        encoded["trip_id"] = saved["trip_id"]
        return encoded


    except HTTPException:
        raise
    except DestinationResearchProviderError as error:
        return _logged_error_response(
            request,
            error,
            stage="research_destination",
            status_code=502,
            message="Destination research is temporarily unavailable. Please try again shortly.",
            error_code="destination_research_unavailable",
        )
    except Exception as error:
        return _logged_error_response(request, error, stage="langgraph.invoke")

class TripResumeRequest(BaseModel):
    thread_id: str
    answer: str


class BudgetConfirmationRequest(BaseModel):
    thread_id: str
    category_allocations: dict[str, float]
    activity_costs: dict[str, object] = Field(default_factory=dict)
    cost_option_selections: list[dict] = Field(default_factory=list)


class BudgetRegenerationRequest(BaseModel):
    thread_id: str


@app.post("/api/resume-trip")
def resume_trip(
    payload: TripResumeRequest,
    request: Request,
    current_user: AuthenticatedUser = Depends(get_current_user),
):

    owned_trip = get_trip_by_thread(current_user.id, payload.thread_id)

    config = {
        "configurable": {
            "thread_id": payload.thread_id,
        }
    }

    current_state = travel_request_graph.get_state(config).values
    if current_state.get("status") == "budget_review":
        raise HTTPException(
            status_code=409,
            detail="Confirm the budget with /api/confirm-budget before itinerary generation.",
        )

    try:

        result = travel_request_graph.invoke(
            Command(
                resume=payload.answer
            ),
            config=config,
        )

        interrupts = result.get(
            "__interrupt__",
            []
        )

        clarification = None

        if interrupts:
            clarification = (
                interrupts[0].value
            )

        response = {
            "thread_id":
                payload.thread_id,
            "trip_id": owned_trip["trip_id"],

            "status":
                result.get("status"),

            "clarification":
                clarification,

            "final_trip":
                result.get("final_trip"),

            "destination_research":
                result.get(
                    "destination_research"
                ),

            "weather_context":
                result.get(
                    "weather_context"
                ),

            "activity_intelligence":
                result.get(
                    "activity_intelligence"
                ),

            "travel_matrix":
                result.get(
                    "travel_matrix"
                ),

            "optimized_itinerary":
                result.get(
                    "optimized_itinerary"
                ),

            "budget_allocation": result.get("budget_allocation"),
            "cost_research": result.get("cost_research"),
        }

        encoded = jsonable_encoder(response)
        save_trip(current_user.id, owned_trip["trip_id"], payload.thread_id, str(result.get("status") or "processing"), encoded)
        return encoded

    except HTTPException:
        raise
    except Exception as error:
        return _logged_error_response(request, error, stage="langgraph.resume")


@app.post("/api/regenerate-budget")
def regenerate_budget(
    payload: BudgetRegenerationRequest,
    request: Request,
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    owned_trip = get_trip_by_thread(current_user.id, payload.thread_id)
    config = {"configurable": {"thread_id": payload.thread_id}}
    snapshot = travel_request_graph.get_state(config)
    state = snapshot.values
    if state.get("status") != "budget_review":
        raise HTTPException(status_code=409, detail="This trip is not awaiting budget review.")

    proposal = build_budget_allocation(
        trip=state["final_trip"],
        cost_estimates=state.get("budget_cost_estimates", []),
    )
    try:
        return {
            "thread_id": payload.thread_id,
            "trip_id": owned_trip["trip_id"],
            "status": "budget_review",
            "final_trip": state.get("final_trip"),
            "destination_research": state.get("destination_research"),
            "weather_context": state.get("weather_context"),
            "activity_intelligence": state.get("activity_intelligence"),
            "travel_matrix": state.get("travel_matrix"),
            "cost_research": state.get("cost_research"),
            "budget_allocation": proposal.model_dump(mode="json"),
        }
    except HTTPException:
        raise
    except Exception as error:
        return _logged_error_response(request, error, stage="regenerate_budget")


@app.post("/api/confirm-budget")
def confirm_budget(
    payload: BudgetConfirmationRequest,
    request: Request,
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    owned_trip = get_trip_by_thread(current_user.id, payload.thread_id)
    config = {"configurable": {"thread_id": payload.thread_id}}
    snapshot = travel_request_graph.get_state(config)
    state = snapshot.values
    if state.get("status") != "budget_review" or "budget_allocation" not in state:
        raise HTTPException(status_code=409, detail="This trip is not awaiting budget review.")

    try:
        trip = state.get("final_trip")
        research = state.get("cost_research")
        selected_estimates = resolve_cost_option_selections(
            research.options if research else [], payload.cost_option_selections, trip,
        )
        if selected_estimates:
            selected_categories = {estimate.category for estimate in selected_estimates}
            baseline = [
                estimate for estimate in state.get("budget_cost_estimates", [])
                if estimate.category not in selected_categories
            ]
            proposed = build_budget_allocation(trip, baseline + selected_estimates)
        else:
            proposed = state["budget_allocation"]
        approved = apply_budget_edits(
            proposed,
            payload.category_allocations,
        )
        activity_intelligence = state.get("activity_intelligence")
        activity_names = {item.name for item in activity_intelligence.activities} if activity_intelligence else set()
        unknown_activity_costs = set(payload.activity_costs) - activity_names
        if unknown_activity_costs:
            raise ValueError("Manual activity costs contain an unknown activity.")
        for name, amount in payload.activity_costs.items():
            if isinstance(amount, bool):
                raise ValueError(f"Manual activity cost for {name} must be finite and non-negative.")
            try:
                numeric_amount = float(amount)
            except (TypeError, ValueError) as error:
                raise ValueError(f"Manual activity cost for {name} must be a valid amount.") from error
            if not isfinite(numeric_amount) or numeric_amount < 0:
                raise ValueError(f"Manual activity cost for {name} must be finite and non-negative.")
        matrix = state.get("travel_matrix")
        route_names = set(matrix.locations) if matrix else set()
        activity_by_name = {
            item.name: item
            for item in (activity_intelligence.activities if activity_intelligence else [])
        }
        activity_cap = approved.amount_for("activities_attractions")
        feasible_prices = []
        provisional_candidates = []
        for name in route_names:
            activity = activity_by_name.get(name)
            if activity is None or activity.estimated_duration_minutes is None or activity.estimated_duration_minutes > 600:
                continue
            if name in payload.activity_costs:
                amount = float(payload.activity_costs[name])
                currency = trip.currency
                basis = "per_traveler"
            else:
                amount = activity.estimated_cost
                currency = activity.currency
                basis = activity.cost_basis
            if amount is None or not currency or currency.upper() != approved.currency.upper():
                # Unknown or incompatible prices may be scheduled only as clearly
                # provisional suggestions. They are never counted as free or as
                # approved spend by the optimizer.
                provisional_candidates.append(name)
                continue
            trip_cost = amount * (trip.travelers if basis == "per_traveler" else 1)
            if trip_cost <= activity_cap + 0.01:
                feasible_prices.append(name)
            # Known prices over the cap remain ineligible; do not turn these into
            # provisional suggestions that could imply approval to spend.
        if not feasible_prices and not provisional_candidates:
            raise ValueError(
                "No resolved activity has a known cost that fits the approved activity cap, "
                "and no schedulable activity has an unknown price for a provisional itinerary. "
                "Enter a manual estimated admission price in the trip currency for at least one activity, "
                "or adjust the activity cap. Unknown prices are not treated as free."
            )
        edits = {
            item.category: item.allocated_amount
            for item in approved.categories
        }
        result = travel_request_graph.invoke(
            Command(resume={
                "category_allocations": edits,
                "activity_costs": payload.activity_costs,
                "cost_option_selections": payload.cost_option_selections,
            }),
            config=config,
        )
        interrupts = result.get("__interrupt__", [])
        response = {
            "thread_id": payload.thread_id,
            "trip_id": owned_trip["trip_id"],
            "status": result.get("status"),
            "clarification": interrupts[0].value if interrupts else None,
            "final_trip": result.get("final_trip"),
            "destination_research": result.get("destination_research"),
            "weather_context": result.get("weather_context"),
            "activity_intelligence": result.get("activity_intelligence"),
            "travel_matrix": result.get("travel_matrix"),
            "optimized_itinerary": result.get("optimized_itinerary"),
            "budget_allocation": result.get("budget_allocation"),
            "cost_research": result.get("cost_research"),
        }
        encoded = jsonable_encoder(response)
        save_trip(current_user.id, owned_trip["trip_id"], payload.thread_id, str(result.get("status") or "processing"), encoded)
        return encoded
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except HTTPException:
        raise
    except Exception as error:
        return _logged_error_response(request, error, stage="confirm_budget")


@app.exception_handler(Exception)
async def handle_unexpected_exception(request: Request, error: Exception):
    return _logged_error_response(
        request,
        error,
        stage=workflow_stage_var.get() or "unhandled_request",
    )
