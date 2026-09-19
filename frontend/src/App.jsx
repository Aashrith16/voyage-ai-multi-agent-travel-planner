import { useState } from "react";
import TripMap from "./components/TripMap";
import {
  Plane,
  Sparkles,
  MapPin,
  CalendarDays,
  Users,
  WalletCards,
  CloudSun,
  Route,
  CheckCircle2,
  LoaderCircle,
  AlertCircle,
} from "lucide-react";

import "./App.css";


const API_URL =
  "http://127.0.0.1:8000/api/plan-trip";

function minutesToTime(totalMinutes) {
  const hours = Math.floor(totalMinutes / 60);
  const minutes = totalMinutes % 60;

  return `${String(hours).padStart(2, "0")}:${String(
    minutes
  ).padStart(2, "0")}`;
}


function buildDaySchedule(
  activities,
  startMinutes = 9 * 60
) {
  let currentTime = startMinutes;

  return activities.map((activity) => {
    const travelMinutes =
      activity.travel_from_previous_minutes || 0;

    currentTime += travelMinutes;

    const startTime = currentTime;

    const duration =
      activity.estimated_duration_minutes || 0;

    const endTime =
      startTime + duration;

    currentTime = endTime;

    return {
      ...activity,

      start_time:
        minutesToTime(startTime),

      end_time:
        minutesToTime(endTime),
    };
  });
}


function App() {
  const [request, setRequest] = useState(
    "Plan a trip from Hyderabad to Tokyo from 10 December 2026 to 16 December 2026 for 2 people. My total budget is 200000 rupees. I like anime, technology and Japanese food."
  );

  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");


  const planTrip = async () => {
    if (!request.trim()) {
      setError("Please describe your trip first.");
      return;
    }

    setLoading(true);
    setError("");
    setResult(null);

    try {
      const response = await fetch(API_URL, {
        method: "POST",

        headers: {
          "Content-Type": "application/json",
        },

        body: JSON.stringify({
          request: request,
        }),
      });


      if (!response.ok) {
        const errorData = await response.json();

        throw new Error(
          errorData.detail ||
            "VoyageAI could not create the trip."
        );
      }


      const data = await response.json();

      setResult(data);
    } catch (err) {
      setError(
        err.message ||
          "Could not connect to VoyageAI."
      );
    } finally {
      setLoading(false);
    }
  };


  const trip = result?.final_trip;
  const research = result?.destination_research;
  const weather = result?.weather_context;
  const itinerary = result?.optimized_itinerary;

  const activityIntelligence =
    result?.activity_intelligence;


  return (
    <div className="app">

      {/* NAVBAR */}

      <nav className="navbar">
        <div className="brand">
          <div className="brand-icon">
            <Plane size={22} />
          </div>

          <div>
            <div className="brand-name">
              VoyageAI
            </div>

            <div className="brand-subtitle">
              Multi-Agent Travel Intelligence
            </div>
          </div>
        </div>

        <div className="ai-badge">
          <Sparkles size={16} />
          AI Travel Planner
        </div>
      </nav>


      {/* HERO */}

      <main className="main">

        <section className="hero">
          <div className="hero-badge">
            <Sparkles size={16} />
            Intelligent trip planning
          </div>

          <h1>
            Plan smarter journeys with
            <span> VoyageAI</span>
          </h1>

          <p className="hero-description">
            Tell VoyageAI where you want to go.
            Our multi-agent system researches,
            analyzes weather, resolves real places,
            calculates routes and mathematically
            optimizes your itinerary.
          </p>


          {/* INPUT */}

          <div className="planner-card">
            <label>
              Describe your trip
            </label>

            <textarea
              value={request}
              onChange={(event) =>
                setRequest(event.target.value)
              }
              placeholder="Example: Plan a 7-day Tokyo trip from Hyderabad for 2 people..."
              rows={6}
              disabled={loading}
            />

            <div className="planner-bottom">

              <div className="planner-hint">
                Include destination, dates,
                travelers, budget and interests.
              </div>

              <button
                onClick={planTrip}
                disabled={loading}
                className="plan-button"
              >
                {loading ? (
                  <>
                    <LoaderCircle
                      size={18}
                      className="spinner"
                    />

                    Planning your trip...
                  </>
                ) : (
                  <>
                    <Sparkles size={18} />
                    Plan my trip
                  </>
                )}
              </button>

            </div>
          </div>
        </section>


        {/* LOADING */}

        {loading && (
          <section className="agent-panel">

            <div className="section-heading">
              <h2>
                VoyageAI agents are working
              </h2>

              <p>
                This may take a little time because
                several live services are being
                queried.
              </p>
            </div>

            <div className="agent-grid">

              <AgentStep
                title="Request Agent"
                description="Understanding your travel request"
              />

              <AgentStep
                title="Research Agent"
                description="Researching destination intelligence"
              />

              <AgentStep
                title="Weather Agent"
                description="Analyzing travel weather"
              />

              <AgentStep
                title="Place Resolver"
                description="Finding real geographic locations"
              />

              <AgentStep
                title="Routing Engine"
                description="Calculating travel-time matrix"
              />

              <AgentStep
                title="OR-Tools Optimizer"
                description="Optimizing your itinerary"
              />

            </div>
          </section>
        )}


        {/* ERROR */}

        {error && (
          <div className="error-box">
            <AlertCircle size={20} />
            {error}
          </div>
        )}


        {/* RESULTS */}

        {result && (
          <div className="results">

            <section className="result-header">

              <div>
                <div className="complete-badge">
                  <CheckCircle2 size={16} />
                  Planning complete
                </div>

                <h2>
                  {trip?.destination ||
                    "Your optimized trip"}
                </h2>

                <p>
                  VoyageAI generated this itinerary
                  using your preferences and live
                  travel intelligence.
                </p>
              </div>

            </section>


            {/* TRIP SUMMARY */}

            {trip && (
              <section className="summary-grid">

                <SummaryCard
                  icon={<MapPin />}
                  label="Destination"
                  value={trip.destination}
                />

                <SummaryCard
                  icon={<CalendarDays />}
                  label="Travel Dates"
                  value={`${trip.departure_date} → ${trip.return_date}`}
                />

                <SummaryCard
                  icon={<Users />}
                  label="Travelers"
                  value={trip.travelers}
                />

                <SummaryCard
                  icon={<WalletCards />}
                  label="Budget"
                  value={`${trip.currency} ${Number(
                    trip.budget
                  ).toLocaleString()}`}
                />

              </section>
            )}


            {/* RESEARCH */}

            {research && (
              <section className="content-card">

                <div className="card-title">
                  <MapPin size={20} />
                  Destination Intelligence
                </div>

                <p className="research-summary">
                  {research.summary}
                </p>

                <div className="recommendation-grid">

                  {research.recommendations?.map(
                    (item, index) => (
                      <div
                        className="recommendation"
                        key={index}
                      >
                        <span className="recommendation-number">
                          {index + 1}
                        </span>

                        <div>
                          <h3>
                            {item.name}
                          </h3>

                          <span className="category">
                            {item.category}
                          </span>

                          <p>
                            {
                              item.why_recommended
                            }
                          </p>
                        </div>
                      </div>
                    )
                  )}

                </div>
              </section>
            )}


            {/* WEATHER */}

            {weather && (
              <section className="content-card">

                <div className="card-title">
                  <CloudSun size={20} />
                  Weather Intelligence
                </div>

                <div className="weather-grid">

                  {weather.risks?.map(
                    (risk, index) => (
                      <div
                        className="weather-card"
                        key={index}
                      >
                        <strong>
                          {risk.date}
                        </strong>

                        <span>
                          Rain:
                          <b>
                            {" "}
                            {risk.rain_risk}
                          </b>
                        </span>

                        <span>
                          Temperature:
                          <b>
                            {" "}
                            {
                              risk.temperature_risk
                            }
                          </b>
                        </span>

                        <span>
                          Outdoors:
                          <b>
                            {" "}
                            {
                              risk.outdoor_suitability
                            }
                          </b>
                        </span>
                      </div>
                    )
                  )}

                </div>
              </section>
            )}


            {/* ITINERARY */}

            {itinerary && (
              <section className="content-card">

                <div className="card-title">
                  <Route size={20} />
                  Optimized Itinerary
                </div>


                <div className="days">

                  {itinerary.days?.map(
                    (day) => (
                      <div
                        className="day-card"
                        key={day.day_number}
                      >

                        <div className="day-heading">
                          <div>
                            <span className="day-label">
                              DAY
                            </span>

                            <h3>
                              {day.day_number}
                            </h3>
                          </div>

                          <div className="day-stats">
                            <span>
                              {
                                day.total_activity_minutes
                              }{" "}
                              min activities
                            </span>

                            <span>
                              {
                                day.total_travel_minutes
                              }{" "}
                              min travel
                            </span>
                          </div>
                        </div>


                        {day.weather_suitability && (
                          <div className="day-weather">
                            Weather suitability:{" "}
                            <strong>
                              {
                                day.weather_suitability
                              }
                            </strong>
                          </div>
                        )}


                        {day.activities?.length ===
                        0 ? (
                          <div className="empty-day">
                            Free / flexible day
                          </div>
                        ) : (
                          <div className="activity-list">

                            {buildDaySchedule(
                              day.activities
                            ).map(
                              (activity, index) => (
                                <div
                                  className="activity-row"
                                  key={index}
                                >
                                  <div className="timeline-dot">
                                    {
                                      activity.sequence
                                    }
                                  </div>

                                  <div className="activity-info">
                                    <h4>
                                      {
                                        activity.name
                                      }
                                    </h4>

                                    <div className="activity-time">
                                      {activity.start_time}
                                      {" – "}
                                      {activity.end_time}
                                    </div>

                                    

                                    <p>
                                      Duration:{" "}
                                      {
                                        activity.estimated_duration_minutes
                                      }{" "}
                                      min
                                    </p>

                                    {activity.travel_from_previous_minutes >
                                      0 && (
                                      <span>
                                        Travel from
                                        previous:{" "}
                                        {
                                          activity.travel_from_previous_minutes
                                        }{" "}
                                        min
                                      </span>
                                    )}
                                  </div>

                                  <div className="preference-score">
                                    {(activity.preference_score *
                                      100).toFixed(
                                      0
                                    )}
                                    %
                                    <small>
                                      match
                                    </small>
                                  </div>
                                </div>
                              )
                            )}

                          </div>
                        )}
                      </div>
                    )
                  )}

                </div>


                <div className="optimizer-footer">

                  <div>
                    <strong>
                      Selected activities
                    </strong>

                    <p>
                      {itinerary.selected_activities
                        ?.join(", ") ||
                        "None"}
                    </p>
                  </div>

                  {itinerary.dropped_activities
                    ?.length > 0 && (
                    <div>
                      <strong>
                        Dropped by optimizer
                      </strong>

                      <p>
                        {itinerary.dropped_activities.join(
                          ", "
                        )}
                      </p>
                    </div>
                  )}

                </div>
              </section>
            )}

            {activityIntelligence &&
              itinerary && (
                <section className="content-card">

                  <div className="card-title">
                    <MapPin size={20} />
                    Interactive Trip Map
                  </div>

                  <p className="map-description">
                    Explore the real locations used by
                    VoyageAI's routing and itinerary
                    optimization system.
                  </p>

                  <TripMap
                    activities={
                      activityIntelligence.activities ||
                      []
                    }
                    itinerary={itinerary}
                  />

                </section>
            )}

          </div>
        )}

      </main>
    </div>
  );
}


function AgentStep({
  title,
  description,
}) {
  return (
    <div className="agent-step">
      <LoaderCircle
        size={20}
        className="spinner"
      />

      <div>
        <strong>{title}</strong>
        <span>{description}</span>
      </div>
    </div>
  );
}


function SummaryCard({
  icon,
  label,
  value,
}) {
  return (
    <div className="summary-card">

      <div className="summary-icon">
        {icon}
      </div>

      <div>
        <span>{label}</span>
        <strong>{value}</strong>
      </div>

    </div>
  );
}


export default App;