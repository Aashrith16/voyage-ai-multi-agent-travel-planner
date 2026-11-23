import assert from 'node:assert/strict'
import test from 'node:test'
import { getActiveNavigationItem } from '../src/lib/navigation.js'

test('main routes highlight only their corresponding navigation item', () => {
  assert.equal(getActiveNavigationItem('/my-trips'), 'trips')
  assert.equal(getActiveNavigationItem('/plan-trip'), 'plan')
  assert.equal(getActiveNavigationItem('/'), 'home')
})

test('nested trip routes highlight their matching navigation item', () => {
  assert.equal(getActiveNavigationItem('/trips/abc-123/budget'), 'budget')
  assert.equal(getActiveNavigationItem('/trips/abc-123/itinerary'), 'itinerary')
  assert.equal(getActiveNavigationItem('/trips/abc-123/map'), 'map')
  assert.equal(getActiveNavigationItem('/trips/abc-123/itinerary/day/2'), null)
  assert.equal(getActiveNavigationItem('/account'), null)
})
