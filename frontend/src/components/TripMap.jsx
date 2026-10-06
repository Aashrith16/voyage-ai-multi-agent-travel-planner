import {
  MapContainer,
  TileLayer,
  Marker,
  Popup,
  Polyline,
  useMap,
} from "react-leaflet";

import {
  useEffect,
  useMemo,
  useState,
} from "react";

import L from "leaflet";

import "leaflet/dist/leaflet.css";


const ROUTE_API =
  "https://voyageai-backend-5pf8.onrender.com/api/route-geometry";


function FitMap({ positions }) {
  const map = useMap();

  useEffect(() => {
    if (!positions.length) {
      return;
    }

    const bounds =
      L.latLngBounds(positions);

    map.fitBounds(bounds, {
      padding: [45, 45],
    });
  }, [map, positions]);

  return null;
}


function createNumberedIcon(
  dayNumber,
  sequence
) {
  return L.divIcon({
    className: "voyage-marker-wrapper",

    html: `
      <div class="voyage-marker">
        <span>D${dayNumber}</span>
        <strong>${sequence}</strong>
      </div>
    `,

    iconSize: [44, 44],
    iconAnchor: [22, 44],
    popupAnchor: [0, -42],
  });
}


function TripMap({
  activities = [],
  itinerary = null,
}) {
  const [routes, setRoutes] =
    useState({});

  const [loadingRoutes, setLoadingRoutes] =
    useState(false);

  const [routeError, setRouteError] =
    useState("");


  const dayGroups = useMemo(() => {
    const coordinateMap =
      new Map();


    for (const activity of activities) {
      if (
        activity.latitude != null &&
        activity.longitude != null
      ) {
        coordinateMap.set(
          activity.name,
          [
            Number(activity.latitude),
            Number(activity.longitude),
          ]
        );
      }
    }


    const groups = [];

    for (
      const day of
      itinerary?.days || []
    ) {
      const resolvedActivities = [];


      for (
        const activity of
        day.activities || []
      ) {
        const position =
          coordinateMap.get(
            activity.name
          );


        if (!position) {
          continue;
        }


        resolvedActivities.push({
          ...activity,

          day_number:
            day.day_number,

          position,
        });
      }


      if (
        resolvedActivities.length
      ) {
        groups.push({
          day_number:
            day.day_number,

          activities:
            resolvedActivities,

          positions:
            resolvedActivities.map(
              (activity) =>
                activity.position
            ),
        });
      }
    }


    return groups;
  }, [activities, itinerary]);


  const allPositions =
    useMemo(
      () =>
        dayGroups.flatMap(
          (day) =>
            day.positions
        ),
      [dayGroups]
    );


  useEffect(() => {
    let cancelled = false;


    async function loadRoutes() {
      setLoadingRoutes(true);
      setRouteError("");


      const newRoutes = {};


      try {
        for (const day of dayGroups) {

          if (
            day.positions.length < 2
          ) {
            newRoutes[
              day.day_number
            ] = {
              geometry:
                day.positions,

              distance_km: 0,

              duration_minutes: 0,
            };

            continue;
          }


          try {
            const response =
              await fetch(
                ROUTE_API,
                {
                  method: "POST",

                  headers: {
                    "Content-Type":
                      "application/json",
                  },

                  body:
                    JSON.stringify({
                      points:
                        day.positions.map(
                          (
                            [
                              latitude,
                              longitude,
                            ]
                          ) => ({
                            latitude,
                            longitude,
                          })
                        ),
                    }),
                }
              );


            if (!response.ok) {
              throw new Error(
                "Route request failed."
              );
            }


            const data =
              await response.json();


            newRoutes[
              day.day_number
            ] = data;

          } catch {
            // Graceful fallback:
            // show straight lines
            // if OSRM is temporarily
            // unavailable.

            newRoutes[
              day.day_number
            ] = {
              geometry:
                day.positions,

              distance_km: null,

              duration_minutes:
                null,
            };
          }
        }


        if (!cancelled) {
          setRoutes(
            newRoutes
          );
        }

      } catch (error) {
        if (!cancelled) {
          setRouteError(
            error.message
          );
        }

      } finally {
        if (!cancelled) {
          setLoadingRoutes(
            false
          );
        }
      }
    }


    if (dayGroups.length) {
      loadRoutes();
    }


    return () => {
      cancelled = true;
    };

  }, [dayGroups]);


  if (!allPositions.length) {
    return (
      <div className="map-empty">
        No resolved itinerary
        locations are available.
      </div>
    );
  }


  return (
    <div className="trip-map-section">

      <MapContainer
        center={
          allPositions[0]
        }
        zoom={12}
        scrollWheelZoom={true}
        className="trip-map"
      >

        <TileLayer
          attribution="&copy; OpenStreetMap contributors"
          url={
            "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          }
        />


        <FitMap
          positions={
            allPositions
          }
        />


        {dayGroups.map(
          (day) => {
            const route =
              routes[
                day.day_number
              ];

            if (
              !route?.geometry ||
              route.geometry.length <
                2
            ) {
              return null;
            }


            return (
              <Polyline
                key={
                  `route-${day.day_number}`
                }
                positions={
                  route.geometry
                }
                pathOptions={{
                  weight: 5,
                  opacity: 0.8,
                }}
              />
            );
          }
        )}


        {dayGroups.flatMap(
          (day) =>
            day.activities.map(
              (
                activity,
                index
              ) => (
                <Marker
                  key={
                    `${activity.day_number}-${activity.name}-${index}`
                  }

                  position={
                    activity.position
                  }

                  icon={
                    createNumberedIcon(
                      activity.day_number,
                      activity.sequence ||
                        index + 1
                    )
                  }
                >

                  <Popup>

                    <div className="map-popup">

                      <strong>
                        {
                          activity.name
                        }
                      </strong>

                      <span>
                        Day{" "}
                        {
                          activity.day_number
                        }{" "}
                        · Stop{" "}
                        {
                          activity.sequence ||
                          index + 1
                        }
                      </span>

                      <span>
                        Duration:{" "}
                        {
                          activity
                            .estimated_duration_minutes
                        }{" "}
                        min
                      </span>


                      {activity.preference_score !=
                        null && (
                        <span>
                          Preference
                          match:{" "}
                          {Math.round(
                            activity
                              .preference_score *
                              100
                          )}
                          %
                        </span>
                      )}

                    </div>

                  </Popup>

                </Marker>
              )
            )
        )}

      </MapContainer>


      {loadingRoutes && (
        <div className="route-status">
          Calculating real road
          routes with OSRM...
        </div>
      )}


      {routeError && (
        <div className="route-warning">
          {routeError}
        </div>
      )}


      <div className="route-summary">

        {dayGroups.map(
          (day) => {
            const route =
              routes[
                day.day_number
              ];


            return (
              <div
                className="route-summary-card"
                key={
                  day.day_number
                }
              >

                <strong>
                  Day{" "}
                  {
                    day.day_number
                  }
                </strong>


                <span>
                  {
                    day.activities
                      .length
                  }{" "}
                  stops
                </span>


                {route
                  ?.distance_km !=
                  null &&
                  route.distance_km >
                    0 && (
                    <span>
                      {
                        route.distance_km
                      }{" "}
                      km
                    </span>
                  )}


                {route
                  ?.duration_minutes !=
                  null &&
                  route.duration_minutes >
                    0 && (
                    <span>
                      {
                        route.duration_minutes
                      }{" "}
                      min driving
                    </span>
                  )}

              </div>
            );
          }
        )}

      </div>

    </div>
  );
}


export default TripMap;