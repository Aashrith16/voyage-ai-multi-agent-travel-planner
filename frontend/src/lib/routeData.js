/** Return geocoded stops in the exact order used by the optimized day. */
export function getOrderedRouteStops(day, activities = []) {
  const coordinatesByName = new Map()
  for (const activity of activities) {
    if (activity.latitude != null && activity.longitude != null) {
      coordinatesByName.set(activity.name, {
        latitude: Number(activity.latitude),
        longitude: Number(activity.longitude),
      })
    }
  }

  return (day?.activities || []).flatMap(activity => {
    const coordinates = coordinatesByName.get(activity.name)
    return coordinates ? [{ ...activity, ...coordinates }] : []
  })
}

/** Keep optimizer totals at route/day level, separate from individual stops. */
export function getDayRouteGroup(day, activities = []) {
  const stops = getOrderedRouteStops(day, activities).map(activity => ({
    ...activity,
    day_number: day?.day_number,
    position: [activity.latitude, activity.longitude],
  }))
  return stops.length ? {
    day_number: day?.day_number,
    total_travel_minutes: day?.total_travel_minutes,
    activities: stops,
    positions: stops.map(activity => activity.position),
  } : null
}

export function getMapEmptyMessage(itinerary) {
  const unscheduledReturnDay = (itinerary?.days || []).find(day =>
    !day?.activities?.length && /return travel day/i.test(day?.schedule_note || ''),
  )
  if (unscheduledReturnDay) {
    return 'No sightseeing stops are scheduled for this return-travel day because the departure time was not provided.'
  }
  return 'No resolved itinerary locations are available.'
}

/** Route leg i-1 is the travel into stop i; the first stop has no leg. */
export function getRouteLegMinutes(route, stopIndex, expectedLegCount) {
  if (stopIndex <= 0) return null
  if (!Array.isArray(route?.legs) || route.legs.length !== expectedLegCount || !route.legs.every(leg => Number.isFinite(leg.duration_minutes) && leg.duration_minutes >= 0)) return null
  const minutes = route?.legs?.[stopIndex - 1]?.duration_minutes
  return Number.isFinite(minutes) && minutes >= 0 ? minutes : null
}

export function getRouteTotalMinutes(route, fallbackMinutes, expectedLegCount) {
  const legs = route?.legs
  if (Array.isArray(legs) && legs.length === expectedLegCount && legs.every(leg => Number.isFinite(leg.duration_minutes) && leg.duration_minutes >= 0)) {
    return Number.isFinite(route.duration_minutes) && route.duration_minutes >= 0
      ? route.duration_minutes
      : legs.reduce((total, leg) => total + leg.duration_minutes, 0)
  }
  return Number.isFinite(fallbackMinutes) && fallbackMinutes >= 0 ? fallbackMinutes : null
}
