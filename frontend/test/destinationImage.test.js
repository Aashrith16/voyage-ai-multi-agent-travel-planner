import assert from 'node:assert/strict'
import test from 'node:test'
import { clearDestinationImageCache, markDestinationImageUnavailable, resolveDestinationImage, shouldShowDestinationPlaceholder } from '../src/lib/destinationImage.js'

const response = body => ({ ok: true, json: async () => body })

function mockedWikimediaFetch({ title, extract, pageimage = `${title.replaceAll(' ', '_')}.jpg` }) {
  const requests = []
  const fetchImpl = async url => {
    const parsed = new URL(url)
    requests.push(parsed)
    if (parsed.hostname === 'en.wikipedia.org') {
      return response({ query: { pages: { 42: {
        pageid: 42,
        index: 1,
        title,
        extract,
        pageimage,
        fullurl: `https://en.wikipedia.org/wiki/${encodeURIComponent(title.replaceAll(' ', '_'))}`,
        thumbnail: { source: `https://upload.wikimedia.org/thumb/${encodeURIComponent(pageimage)}` },
      } } } })
    }
    return response({ query: { pages: { 7: { imageinfo: [{
      thumburl: `https://upload.wikimedia.org/thumb/${encodeURIComponent(pageimage)}`,
      descriptionurl: `https://commons.wikimedia.org/wiki/File:${encodeURIComponent(pageimage)}`,
      extmetadata: {
        LicenseShortName: { value: 'CC BY-SA 4.0' },
        LicenseUrl: { value: 'https://creativecommons.org/licenses/by-sa/4.0/' },
        Artist: { value: '<a>Example photographer</a>' },
      },
    }] } } } })
  }
  return { fetchImpl, requests }
}

test('Bengaluru, Goa and Paris issue independent destination-specific lookups', async () => {
  clearDestinationImageCache()
  const destinations = [
    ['Bengaluru, India', 'Bengaluru', 'Bengaluru is a city in India.'],
    ['Goa, India', 'Goa', 'Goa is a state in India.'],
    ['Paris, France', 'Paris', 'Paris is the capital of France.'],
  ]
  const resolved = await Promise.all(destinations.map(async ([destination, title, extract]) => {
    const { fetchImpl, requests } = mockedWikimediaFetch({ title, extract })
    const image = await resolveDestinationImage(destination, fetchImpl)
    return { destination, image, requests }
  }))

  for (const result of resolved) {
    assert.ok(result.image?.imageUrl)
    assert.match(result.image.sourceUrl, /commons\.wikimedia\.org/)
    assert.equal(result.image.license, 'CC BY-SA 4.0')
    assert.equal(result.requests[0].searchParams.get('gsrsearch'), result.destination)
    assert.match(result.requests[0].searchParams.get('piprop'), /name/)
    assert.equal(result.requests.length, 2)
  }
  assert.equal(new Set(resolved.map(result => result.image.imageUrl)).size, 3)
})

test('arbitrary destination names are searched without a destination-to-URL mapping', async () => {
  clearDestinationImageCache()
  const { fetchImpl, requests } = mockedWikimediaFetch({
    title: 'Kochi',
    extract: 'Kochi is a city in Kerala, India.',
  })
  const image = await resolveDestinationImage('Kochi, Kerala, India', fetchImpl)

  assert.equal(image.destinationTitle, 'Kochi')
  assert.equal(requests[0].searchParams.get('gsrsearch'), 'Kochi, Kerala, India')
})

test('ambiguous or missing destinations safely use the no-image result', async () => {
  clearDestinationImageCache()
  const { fetchImpl, requests } = mockedWikimediaFetch({
    title: 'Springfield',
    extract: 'Springfield may refer to several places.',
  })
  assert.equal(await resolveDestinationImage('Springfield', fetchImpl), null)
  assert.equal(await resolveDestinationImage('   ', fetchImpl), null)
  assert.equal(requests.length, 1)
})

test('API failure is handled and broken image URLs select the neutral placeholder', async () => {
  clearDestinationImageCache()
  const image = await resolveDestinationImage('Delhi, India', async () => ({ ok: false, json: async () => ({}) }))
  assert.equal(image, null)
  assert.equal(shouldShowDestinationPlaceholder(image, false), true)

  const candidate = { imageUrl: 'https://upload.wikimedia.org/broken.jpg' }
  assert.equal(shouldShowDestinationPlaceholder(candidate, true), true)
  assert.equal(shouldShowDestinationPlaceholder(candidate, false), false)

  clearDestinationImageCache()
  const { fetchImpl, requests } = mockedWikimediaFetch({ title: 'Delhi', extract: 'Delhi is a city in India.' })
  const resolved = await resolveDestinationImage('Delhi, India', fetchImpl)
  markDestinationImageUnavailable('Delhi, India')
  assert.equal(shouldShowDestinationPlaceholder(resolved, true), true)
  assert.equal(await resolveDestinationImage('Delhi, India', fetchImpl), null)
  assert.equal(requests.length, 2)
})

test('successful lookups are cached per destination', async () => {
  clearDestinationImageCache()
  const { fetchImpl, requests } = mockedWikimediaFetch({ title: 'Hyderabad', extract: 'Hyderabad is a city in India.' })
  const first = await resolveDestinationImage('Hyderabad, India', fetchImpl)
  const second = await resolveDestinationImage('Hyderabad, India', fetchImpl)

  assert.deepEqual(second, first)
  assert.equal(requests.length, 2)
})

test('transient API failures are not negative-cached and can recover on the next lookup', async () => {
  clearDestinationImageCache()
  const recovered = mockedWikimediaFetch({ title: 'Kyoto', extract: 'Kyoto is a city in Japan.' })
  let calls = 0
  const fetchImpl = async url => {
    calls += 1
    if (calls === 1) return { ok: false, status: 503, json: async () => ({}) }
    return recovered.fetchImpl(url)
  }

  assert.equal(await resolveDestinationImage('Kyoto, Japan', fetchImpl), null)
  const image = await resolveDestinationImage('Kyoto, Japan', fetchImpl)

  assert.equal(image.destinationTitle, 'Kyoto')
  assert.equal(calls, 3)
})

test('Commons dynamic page IDs, continuation metadata, and thumb.wikimedia.org images resolve', async () => {
  clearDestinationImageCache()
  const requests = []
  const fetchImpl = async url => {
    const parsed = new URL(url)
    requests.push(parsed)
    if (parsed.hostname === 'en.wikipedia.org') {
      return response({ query: { pages: { 92381: {
        index: 1,
        title: 'Kyoto',
        extract: 'Kyoto is a city in Japan.',
        pageimage: 'Kyoto_view.jpg',
        fullurl: 'https://en.wikipedia.org/wiki/Kyoto',
        thumbnail: { source: 'https://upload.wikimedia.org/wikipedia/commons/thumb/Kyoto_view.jpg' },
      } } } })
    }
    return response({
      continue: { iicontinue: 'next-item', continue: '||' },
      query: { pages: { 87654321: { imageinfo: [{
        thumburl: 'https://thumb.wikimedia.org/wikipedia/commons/thumb/Kyoto_view.jpg?width=1000&hash=abc',
        url: 'https://upload.wikimedia.org/wikipedia/commons/Kyoto_view.jpg',
        descriptionurl: 'https://commons.wikimedia.org/wiki/File:Kyoto_view.jpg',
        extmetadata: {
          Artist: { value: '<a href="https://commons.wikimedia.org/wiki/User:Photographer">Photographer &amp; Co.</a>' },
          LicenseShortName: { value: 'CC BY-SA 4.0' },
          LicenseUrl: { value: 'https://creativecommons.org/licenses/by-sa/4.0' },
        },
      }] } } },
    })
  }

  const image = await resolveDestinationImage('Kyoto, Japan', fetchImpl)

  assert.equal(requests.length, 2)
  assert.equal(image?.imageUrl, 'https://thumb.wikimedia.org/wikipedia/commons/thumb/Kyoto_view.jpg?width=1000&hash=abc')
  assert.equal(image?.sourceUrl, 'https://commons.wikimedia.org/wiki/File:Kyoto_view.jpg')
  assert.equal(image?.artist, 'Photographer & Co.')
  assert.equal(image?.license, 'CC BY-SA 4.0')
  assert.equal(image?.licenseUrl, 'https://creativecommons.org/licenses/by-sa/4.0')
  assert.equal(shouldShowDestinationPlaceholder(image, false), false)
})
