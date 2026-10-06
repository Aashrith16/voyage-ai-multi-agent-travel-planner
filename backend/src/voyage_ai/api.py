from uuid import uuid4
import httpx

from fastapi import FastAPI, HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from voyage_ai.graph.workflow import (
    travel_request_graph,
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

@app.post("/api/route-geometry")
def route_geometry(
    payload: RouteGeometryRequest,
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
        }


    except Exception as error:
        raise HTTPException(
            status_code=502,
            detail=(
                "Could not retrieve OSRM route: "
                f"{error}"
            ),
        )

# ==================================================
# TRIP PLANNING ENDPOINT
# ==================================================

@app.post("/api/plan-trip")
def plan_trip(
    payload: TripPlanningRequest,
):

    thread_id = (
        payload.thread_id
        or str(uuid4())
    )


    config = {
        "configurable": {
            "thread_id": thread_id,
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


        response = {
            "thread_id": thread_id,

            "status": result.get(
                "status"
            ),

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
        }


        return jsonable_encoder(
            response
        )


    except Exception as error:

        raise HTTPException(
            status_code=500,
            detail=str(error),
        )