import assert from 'node:assert/strict'
import test from 'node:test'
import { getDayRouteGroup, getMapEmptyMessage, getOrderedRouteStops, getRouteLegMinutes, getRouteTotalMinutes } from '../src/lib/routeData.js'

test('multi-day route stops use each optimized day order, not discovery order', () => {
  const activities = [
    { name: 'A', latitude: 1, longitude: 1 },
    { name: 'B', latitude: 2, longitude: 2 },
    { name: 'C', latitude: 3, longitude: 3 },
  ]
  const dayOne = { day_number: 1, activities: [{ name: 'B' }, { name: 'A' }] }
  const dayTwo = { day_number: 2, activities: [{ name: 'C' }, { name: 'B' }] }

  assert.deepEqual(getOrderedRouteStops(dayOne, activities).map(stop => stop.name), ['B', 'A'])
  assert.deepEqual(getOrderedRouteStops(dayTwo, activities).map(stop => stop.name), ['C', 'B'])
})

test('route total and activity travel times come from the same complete leg list', () => {
  const route = { duration_minutes: 17.2, legs: [{ duration_minutes: 7 }, { duration_minutes: 10 }] }
  assert.equal(getRouteLegMinutes(route, 0, 2), null)
  assert.equal(getRouteLegMinutes(route, 1, 2), 7)
  assert.equal(getRouteLegMinutes(route, 2, 2), 10)
  assert.equal(getRouteTotalMinutes(route, 99, 2), 17.2)
})

test('missing route legs fall back to optimizer total; missing leg times stay unavailable', () => {
  const incomplete = { duration_minutes: 17, legs: [{ duration_minutes: 7 }, {}] }
  assert.equal(getRouteLegMinutes(incomplete, 1, 2), null)
  assert.equal(getRouteLegMinutes(incomplete, 2), null)
  assert.equal(getRouteTotalMinutes(incomplete, 17, 2), 17)
  assert.equal(getRouteTotalMinutes(null, null, 2), null)
})

test('map route group keeps daily driving total separate from stop records', () => {
  const day = {
    day_number: 2,
    total_travel_minutes: 24.5,
    activities: [{ name: 'B' }, { name: 'A' }],
  }
  const activities = [
    { name: 'A', latitude: 1, longitude: 2 },
    { name: 'B', latitude: 3, longitude: 4 },
  ]
  const group = getDayRouteGroup(day, activities)

  assert.equal(group.total_travel_minutes, 24.5)
  assert.deepEqual(group.activities.map(stop => stop.name), ['B', 'A'])
  assert.ok(group.activities.every(stop => !Object.hasOwn(stop, 'total_travel_minutes')))
  assert.deepEqual(group.positions, [[3, 4], [1, 2]])
})

test('map explains intentionally unscheduled return days and preserves the unresolved-location message', () => {
  assert.match(
    getMapEmptyMessage({ days: [{
      activities: [],
      schedule_note: 'Return travel day: no local activities scheduled because departure time was not provided.',
    }] }),
    /return-travel day.*departure time was not provided/i,
  )
  assert.equal(
    getMapEmptyMessage({ days: [{ activities: [{ name: 'Unresolved stop' }] }] }),
    'No resolved itinerary locations are available.',
  )
})
