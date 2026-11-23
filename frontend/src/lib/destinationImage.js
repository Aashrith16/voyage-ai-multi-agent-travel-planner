const WIKIPEDIA_API = 'https://en.wikipedia.org/w/api.php'
const WIKIMEDIA_COMMONS_API = 'https://commons.wikimedia.org/w/api.php'
const CACHE_TTL_MS = 24 * 60 * 60 * 1000
const EMPTY_CACHE_TTL_MS = 60 * 1000
const REQUEST_TIMEOUT_MS = 5000
const MAX_CACHE_ENTRIES = 100
const imageCache = new Map()
const imageRequests = new Map()

class TransientImageLookupError extends Error {}

const normalizeText = value => String(value || '')
  .normalize('NFKD')
  .replace(/[\u0300-\u036f]/g, '')
  .toLocaleLowerCase()
  .replace(/[^\p{L}\p{N}]+/gu, ' ')
  .trim()

const tokensFor = value => normalizeText(value)
  .split(/\s+/)
  .filter(token => token.length > 1 && !['the', 'of', 'and', 'in', 'at'].includes(token))

function buildWikipediaSearch(destination) {
  const params = new URLSearchParams({
    action: 'query',
    generator: 'search',
    gsrsearch: destination,
    gsrnamespace: '0',
    gsrlimit: '6',
    prop: 'pageimages|extracts|info',
    exintro: '1',
    explaintext: '1',
    inprop: 'url',
    piprop: 'thumbnail|name',
    pithumbsize: '1000',
    format: 'json',
    origin: '*',
  })
  return `${WIKIPEDIA_API}?${params}`
}

function buildCommonsImageInfo(pageImage) {
  const params = new URLSearchParams({
    action: 'query',
    titles: `File:${pageImage}`,
    prop: 'imageinfo',
    iiprop: 'url|extmetadata',
    iiurlwidth: '1000',
    format: 'json',
    origin: '*',
  })
  return `${WIKIMEDIA_COMMONS_API}?${params}`
}

async function fetchJson(url, fetchImpl) {
  const controller = new AbortController()
  const timeoutId = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS)
  try {
    let response
    try {
      response = await fetchImpl(url, {
        method: 'GET',
        headers: { Accept: 'application/json' },
        signal: controller.signal,
      })
    } catch {
      throw new TransientImageLookupError('Wikimedia request failed.')
    }
    if (!response.ok) {
      if (response.status === 429 || response.status >= 500) {
        throw new TransientImageLookupError('Wikimedia request is temporarily unavailable.')
      }
      return null
    }
    try {
      return await response.json()
    } catch {
      throw new TransientImageLookupError('Wikimedia returned an invalid response.')
    }
  } finally {
    clearTimeout(timeoutId)
  }
}

function matchingDestinationPage(pages, destination) {
  const [primary, ...contextParts] = destination.split(',').map(part => part.trim()).filter(Boolean)
  const primaryTokens = tokensFor(primary)
  const contextTokens = tokensFor(contextParts.join(' '))
  if (!primaryTokens.length) return null

  const candidates = Object.values(pages || {}).filter(page => {
    const titleTokens = new Set(tokensFor(page.title))
    if (!primaryTokens.every(token => titleTokens.has(token))) return false
    const description = normalizeText(page.extract || '')
    if (/\b(may refer to|can refer to|disambiguation)\b/.test(description)
      || normalizeText(page.title).includes('disambiguation')) return false
    const contextTokensFound = new Set(tokensFor(`${page.title} ${description}`))
    return contextTokens.every(token => contextTokensFound.has(token))
  })
  if (!candidates.length) return null

  candidates.sort((left, right) => {
    const leftExact = normalizeText(left.title) === normalizeText(primary) ? 1 : 0
    const rightExact = normalizeText(right.title) === normalizeText(primary) ? 1 : 0
    return rightExact - leftExact || (left.index || 0) - (right.index || 0)
  })

  const best = candidates[0]
  const bestIsExact = normalizeText(best.title) === normalizeText(primary)
  const hasUniqueBest = bestIsExact || candidates.length === 1
  return hasUniqueBest ? best : null
}

function plainText(value) {
  return String(value || '')
    .replace(/<[^>]*>/g, ' ')
    .replace(/&amp;/gi, '&')
    .replace(/&quot;/gi, '"')
    .replace(/&#039;|&apos;/gi, "'")
    .replace(/&lt;/gi, '<')
    .replace(/&gt;/gi, '>')
    .replace(/\s+/g, ' ')
    .trim()
}

function isTrustedUrl(value, hosts) {
  try {
    const parsed = new URL(value)
    return parsed.protocol === 'https:' && hosts.includes(parsed.hostname)
  } catch {
    return false
  }
}

async function lookupDestinationImage(destination, fetchImpl) {
  try {
    const articleData = await fetchJson(buildWikipediaSearch(destination), fetchImpl)
    const article = matchingDestinationPage(articleData?.query?.pages, destination)
    if (!article?.pageimage || !article?.thumbnail?.source) return null

    const imageData = await fetchJson(buildCommonsImageInfo(article.pageimage), fetchImpl)
    const image = Object.values(imageData?.query?.pages || {})[0]?.imageinfo?.[0]
    const metadata = image?.extmetadata || {}
    const license = plainText(metadata.LicenseShortName?.value)
    const sourceUrl = image?.descriptionurl
    const imageUrl = image?.thumburl || article.thumbnail.source
    if (!isTrustedUrl(imageUrl, ['upload.wikimedia.org', 'thumb.wikimedia.org'])
      || !isTrustedUrl(sourceUrl, ['commons.wikimedia.org'])
      || !license) return null

    const artist = plainText(metadata.Artist?.value) || plainText(metadata.Credit?.value) || 'Wikimedia Commons contributor'
    const licenseUrl = isTrustedUrl(metadata.LicenseUrl?.value, ['creativecommons.org', 'www.gnu.org'])
      ? metadata.LicenseUrl.value
      : sourceUrl
    return {
      imageUrl,
      sourceUrl,
      articleUrl: article.fullurl,
      destinationTitle: article.title,
      artist,
      license,
      licenseUrl,
    }
  } catch (error) {
    if (error instanceof TransientImageLookupError) throw error
    return null
  }
}

function remember(key, image) {
  if (imageCache.size >= MAX_CACHE_ENTRIES) {
    const oldestKey = imageCache.keys().next().value
    if (oldestKey) imageCache.delete(oldestKey)
  }
  imageCache.set(key, {
    image,
    expiresAt: Date.now() + (image ? CACHE_TTL_MS : EMPTY_CACHE_TTL_MS),
  })
}

export function resolveDestinationImage(destination, fetchImpl = globalThis.fetch) {
  const value = String(destination || '').trim().replace(/\s+/g, ' ')
  if (!value || typeof fetchImpl !== 'function') return Promise.resolve(null)
  const key = normalizeText(value)
  const cached = imageCache.get(key)
  if (cached && cached.expiresAt > Date.now()) return Promise.resolve(cached.image)
  if (cached) imageCache.delete(key)
  if (imageRequests.has(key)) return imageRequests.get(key)

  const request = lookupDestinationImage(value, fetchImpl)
    .then(image => {
      remember(key, image)
      return image
    })
    .catch(() => null)
    .finally(() => imageRequests.delete(key))
  imageRequests.set(key, request)
  return request
}

export function clearDestinationImageCache() {
  imageCache.clear()
  imageRequests.clear()
}

export function markDestinationImageUnavailable(destination) {
  const key = normalizeText(String(destination || '').trim().replace(/\s+/g, ' '))
  if (key) remember(key, null)
}

export function shouldShowDestinationPlaceholder(image, failed) {
  return !image?.imageUrl || failed
}
