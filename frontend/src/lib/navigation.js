export function getActiveNavigationItem(pathname) {
  if (pathname === '/') return 'home'
  if (pathname === '/plan-trip') return 'plan'
  if (pathname === '/my-trips') return 'trips'

  const tripRoute = pathname.match(/^\/trips\/[^/]+\/(budget|itinerary|map)$/)
  if (tripRoute) return tripRoute[1]
  return null
}
