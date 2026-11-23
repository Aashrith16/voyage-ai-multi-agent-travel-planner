# VoyageAI

VoyageAI is a multi-agent travel planner that turns a natural-language trip request into a researched, budget-reviewed, route-aware itinerary. It combines AI recommendations with location resolution, weather context, cost evidence, and a constraint-based itinerary optimizer.

## Problem

Trip planning is spread across search, maps, weather, budgeting, and scheduling tools. A conversational assistant can suggest places, but suggestions alone do not make a practical itinerary. VoyageAI brings those steps into one workflow and keeps the user in control of category budgets before final optimization.

## Features

- Natural-language trip requests and follow-up conversation memory.
- Destination recommendations researched through Tavily and analyzed by Gemini.
- Weather context from Open-Meteo, with an explicit unavailable state when the provider cannot supply data.
- Place geocoding through Geoapify when configured, with an optional throttled OpenStreetMap Nominatim fallback; driving routes use OSRM.
- Cost research with source evidence, currency, cost basis, confidence, and indicative-price labeling.
- Editable category budget allocation and a budget confirmation checkpoint.
- Multi-day activity selection and ordering with Google OR-Tools, including approved activity caps.
- Saved-trip loading, account ownership checks, and an interactive Leaflet map.

## Workflow and architecture

```text
React + Vite client
        |
        v
FastAPI API -- authentication / saved trips
        |
        v
LangGraph conversation and planning workflow
  1. Understand the request; ask for missing details
  2. Research the destination (Tavily + Gemini)
  3. Fetch weather context (Open-Meteo)
  4. Build activity candidates and resolve place locations
  5. Calculate driving routes (OSRM)
  6. Research indicative trip costs (Tavily)
  7. Pause at budget review for user edits and confirmation
  8. Optimize activity selection and ordering (OR-Tools)
        |
        v
Persisted trip, itinerary, and map views
```

The budget review is an explicit workflow checkpoint. The optimizer uses user-approved category caps. Unknown or incompatible-currency activity prices are not treated as free. Schedule durations and route values are estimates; the application does not claim to know attraction opening hours or flight times when those details were not provided.

## Technology stack

- **Backend:** Python 3.12+, FastAPI, Pydantic, LangGraph, Google GenAI SDK, OR-Tools
- **Frontend:** React, Vite, React Router, Supabase JS, Leaflet, React Leaflet
- **Research and data providers:** Gemini, Tavily, Open-Meteo, Geoapify, OpenStreetMap Nominatim, OSRM
- **Persistence and authentication:** Supabase Postgres and Supabase Auth in configured deployments; local development mode is available without Supabase

## Requirements

- Python 3.12 or newer
- [uv](https://docs.astral.sh/uv/) for backend dependency management
- Node.js and npm
- Gemini and Tavily API credentials for live AI and research functionality
- A Geoapify API key for production geocoding (recommended)
- Supabase project credentials for account authentication and persistent production storage

## Local setup (PowerShell)

### 1. Backend

```powershell
cd backend
Copy-Item .env.example .env
# Add your own provider credentials to backend/.env. Do not commit this file.
uv sync
$env:PYTHONPATH = "src"
uv run uvicorn voyage_ai.api:app --reload --host 127.0.0.1 --port 8000
```

Check the API at `http://127.0.0.1:8000/api/health`. The interactive API documentation is at `http://127.0.0.1:8000/docs`.

### 2. Frontend

In a second terminal:

```powershell
cd frontend
Copy-Item .env.example .env.local
# Set VITE_SUPABASE_URL and VITE_SUPABASE_ANON_KEY when using Supabase Auth.
npm ci
npm run dev
```

Open the Vite URL shown in the terminal, normally `http://localhost:5173`.
`VITE_API_URL` defaults to the local backend URL in development.

When Supabase is not configured, the frontend's local development preview and backend development identity are enabled only in development mode. This mode is not suitable for deployment. Production mode requires proper Supabase configuration and the backend database URL.

## Environment variables

Copy the example files and supply credentials locally. Keep actual secrets out of source control and screenshots.

### Backend (`backend/.env`)

| Variable | Purpose |
| --- | --- |
| `GEMINI_API_KEY` | Gemini request understanding and destination analysis |
| `GEMINI_MODEL` | Optional Gemini model override; defaults to `gemini-3.5-flash-lite` |
| `TAVILY_API_KEY` | Destination and cost research |
| `GEOCODING_PROVIDER` | `auto` (default: Geoapify when its key exists, otherwise Nominatim), `geoapify`, or `nominatim` |
| `GEOAPIFY_API_KEY` | Geoapify geocoding key; recommended for production place resolution |
| `GEOCODING_NOMINATIM_FALLBACK` | Optional opt-in (`false` by default) to use Nominatim after eligible Geoapify errors; provider throttling applies |
| `NOMINATIM_USER_AGENT` | Identifies the application when using Nominatim; use a stable app name and contact in production |
| `NOMINATIM_CONTACT` | Optional contact email supplied to Nominatim |
| `BUDGET_CONTINGENCY_RATE` | Emergency reserve fraction; defaults to `0.10` |
| `VOYAGEAI_ENV` | Set to `development` locally and `production` in deployment |
| `SUPABASE_URL` | Supabase project URL for token verification |
| `SUPABASE_ANON_KEY` | Supabase public/anon key used for legacy token verification when needed |
| `SUPABASE_JWT_SECRET` | Optional legacy HS256 token verification secret; keep private |
| `SUPABASE_DB_URL` | Supabase Postgres connection string; required in production |
| `DATABASE_POOL_SIZE` | Optional database connection pool size; defaults to `8` |

### Frontend (`frontend/.env.local`)

| Variable | Purpose |
| --- | --- |
| `VITE_API_URL` | Backend base URL; use `http://127.0.0.1:8000` locally |
| `VITE_SUPABASE_URL` | Supabase project URL for frontend authentication |
| `VITE_SUPABASE_ANON_KEY` | Supabase publishable/anon key; never put a service-role key in the frontend |

The example files contain blank credential placeholders, not working keys. Geoapify is selected automatically when `GEOAPIFY_API_KEY` is configured. Without it, the application uses Nominatim, which is subject to the [public service usage policy](https://operations.osmfoundation.org/policies/nominatim/); the backend throttles requests within each process and caches successful lookups. Production should use Geoapify to avoid dependence on the public Nominatim service. Do not enable Nominatim fallback for HTTP 429/629 responses. Route and weather integrations do not require keys in the current configuration.

## Tests and quality checks

From `backend`:

```powershell
$env:PYTHONPATH = "src"
.\.venv\Scripts\python.exe -m unittest discover -s . -p "test_*.py" -v
.\.venv\Scripts\python.exe -m compileall -q src
```

The backend tests are deterministic and mock external providers. Optional live integration tests are guarded by explicit environment flags; see [backend/TESTING.md](backend/TESTING.md). Do not enable live tests unless you intend to make provider requests.

From `frontend`:

```powershell
node --test test/routeData.test.js
npm run lint
npm run build
```

There is no separate frontend test script at present; the route-data regression tests use Node's built-in test runner.

## Screenshots

No screenshot files are currently included in the repository. Add verified, current screenshots under `docs/screenshots/` before replacing these placeholders.

- `[Screenshot placeholder: Home and destination discovery]`
- `[Screenshot placeholder: Budget review and evidence]`
- `[Screenshot placeholder: Saved multi-day itinerary]`
- `[Screenshot placeholder: Interactive trip map]`

## Current limitations and future improvements

- Third-party weather, geocoding, routing, and research providers can be rate-limited or temporarily unavailable; unavailable data is surfaced where supported.
- Driving routes are not public-transit directions. Traffic, attraction hours, meals, queues, transfers, and flight schedules are not fully modeled.
- Cost research is indicative evidence, not a booking quote or a confirmed price. Currencies are kept distinct; users should verify prices before travel.
- The arrival-day schedule is provisional when arrival time is unknown, and return dates without a departure time are left unscheduled.
- Saved trips created before newer validation and scheduling rules are not retroactively changed. In particular, older saved itineraries may still contain a lodging recommendation as an activity.
- Live provider behavior and production Supabase deployment require credentials and environment-specific verification. Automated tests do not establish production readiness.

Possible future work includes richer schedule availability inputs, transit routing, broader real-provider integration tests, and presentation-ready screenshots.

## License

No license is currently specified. Add a license before redistributing this project.
