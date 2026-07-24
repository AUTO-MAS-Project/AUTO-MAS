export type AppBackgroundSource = 'default' | 'user' | 'plugin'
export type AppBackgroundFallbackReason =
  | 'none'
  | 'disabled'
  | 'missing-image'
  | 'unsafe-url'
  | 'image-load-failed'

export interface ResolvedAppBackground {
  source: AppBackgroundSource
  enabled: boolean
  imageUrl: string
  blurPx: number
  brightness: number
  opacity: number
  overlayOpacity: number
  cardOpacity: number
  panelOpacity: number
  elevatedOpacity: number
  siderOpacity: number
  position: 'center center' | 'center top' | 'center bottom'
  fit: 'cover' | 'contain'
  fallbackReason: AppBackgroundFallbackReason
}

type UnknownRecord = Record<string, unknown>

const DEFAULT_API_BASE = 'http://127.0.0.1:36163'
const BACKGROUND_SOURCE_PRIORITY: AppBackgroundSource[] = ['user', 'plugin', 'default']
const SAFE_BACKGROUND_API_PREFIXES = [
  '/api/plugins/frontend/background/',
  '/api/plugins/assets/',
  '/api/frontend/background/',
  '/api/settings/frontend/background/',
]

export const DEFAULT_APP_BACKGROUND: ResolvedAppBackground = {
  source: 'default',
  enabled: false,
  imageUrl: '',
  blurPx: 0,
  brightness: 100,
  opacity: 100,
  overlayOpacity: 0,
  cardOpacity: 100,
  panelOpacity: 100,
  elevatedOpacity: 100,
  siderOpacity: 100,
  position: 'center center',
  fit: 'cover',
  fallbackReason: 'disabled',
}

const isRecord = (value: unknown): value is UnknownRecord =>
  typeof value === 'object' && value !== null && !Array.isArray(value)

const normalizeSource = (value: unknown): AppBackgroundSource | null => {
  const source = String(value || '')
    .trim()
    .toLowerCase()
  return source === 'default' || source === 'user' || source === 'plugin' ? source : null
}

const toNumber = (value: unknown, fallback: number) => {
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : fallback
}

const toPercent = (value: unknown, fallback: number, max = 100) => {
  const parsed = toNumber(value, fallback)
  const percentage = parsed > 0 && parsed <= 1 ? parsed * 100 : parsed
  return Math.max(0, Math.min(max, percentage))
}

const toBlur = (value: unknown) => Math.max(0, Math.min(40, toNumber(value, 0)))

const toPosition = (value: unknown): ResolvedAppBackground['position'] => {
  if (value === 'top' || value === 'center top') return 'center top'
  if (value === 'bottom' || value === 'center bottom') return 'center bottom'
  return 'center center'
}

const toFit = (value: unknown): ResolvedAppBackground['fit'] =>
  value === 'contain' ? 'contain' : 'cover'

const readValue = (candidate: UnknownRecord, envelope: UnknownRecord, ...keys: string[]) => {
  for (const key of keys) {
    if (candidate[key] !== undefined) return candidate[key]
  }
  for (const key of keys) {
    if (envelope[key] !== undefined) return envelope[key]
  }
  return undefined
}

const getNestedCandidate = (
  envelope: UnknownRecord,
  source: AppBackgroundSource
): UnknownRecord | null => {
  const direct = envelope[source]
  if (isRecord(direct)) return direct

  const sources = envelope.sources
  if (isRecord(sources) && isRecord(sources[source])) return sources[source]

  const named = envelope[`${source}_background`]
  return isRecord(named) ? named : null
}

const hasNestedCandidates = (envelope: UnknownRecord) =>
  BACKGROUND_SOURCE_PRIORITY.some(source => getNestedCandidate(envelope, source) !== null)

const buildSourceOrder = (envelope: UnknownRecord) => {
  const selected = normalizeSource(envelope.active_source ?? envelope.activeSource)
  if (!selected) return BACKGROUND_SOURCE_PRIORITY
  return [selected, ...BACKGROUND_SOURCE_PRIORITY.filter(source => source !== selected)]
}

export const resolveSafeBackgroundUrl = (value: unknown, apiBase = DEFAULT_API_BASE): string => {
  const raw = typeof value === 'string' ? value.trim() : ''
  const hasUnsafeCharacter = [...raw].some(
    character => character === '\\' || character.charCodeAt(0) < 32
  )
  if (!raw || raw.startsWith('//') || hasUnsafeCharacter) return ''

  try {
    const backend = new URL(apiBase || DEFAULT_API_BASE)
    if (!['http:', 'https:'].includes(backend.protocol)) return ''

    const backendRoot = new URL('/', backend)
    const target = new URL(raw, backendRoot)
    if (target.origin !== backendRoot.origin || !['http:', 'https:'].includes(target.protocol)) {
      return ''
    }
    if (target.username || target.password) return ''
    if (!SAFE_BACKGROUND_API_PREFIXES.some(prefix => target.pathname.startsWith(prefix))) {
      return ''
    }

    target.hash = ''
    return target.toString()
  } catch {
    return ''
  }
}

const resolveCandidate = (
  source: AppBackgroundSource,
  candidate: UnknownRecord,
  envelope: UnknownRecord,
  apiBase: string
): ResolvedAppBackground | AppBackgroundFallbackReason => {
  if (candidate.enabled === false) return 'disabled'

  const imageValue = readValue(candidate, envelope, 'image_url', 'imageUrl')
  if (typeof imageValue !== 'string' || !imageValue.trim()) return 'missing-image'

  const imageUrl = resolveSafeBackgroundUrl(imageValue, apiBase)
  if (!imageUrl) return 'unsafe-url'

  const cardOpacity = toPercent(readValue(candidate, envelope, 'card_opacity', 'cardOpacity'), 92)

  return {
    source,
    enabled: true,
    imageUrl,
    blurPx: toBlur(readValue(candidate, envelope, 'blur_px', 'blurPx')),
    brightness: toPercent(readValue(candidate, envelope, 'brightness'), 100, 160),
    opacity: toPercent(readValue(candidate, envelope, 'opacity'), 100),
    overlayOpacity: toPercent(
      readValue(candidate, envelope, 'overlay_opacity', 'overlayOpacity'),
      0,
      90
    ),
    cardOpacity,
    panelOpacity: toPercent(
      readValue(candidate, envelope, 'panel_opacity', 'panelOpacity'),
      cardOpacity
    ),
    elevatedOpacity: toPercent(
      readValue(candidate, envelope, 'elevated_opacity', 'elevatedOpacity'),
      cardOpacity
    ),
    siderOpacity: toPercent(readValue(candidate, envelope, 'sider_opacity', 'siderOpacity'), 88),
    position: toPosition(readValue(candidate, envelope, 'position')),
    fit: toFit(readValue(candidate, envelope, 'fit')),
    fallbackReason: 'none',
  }
}

export const resolveAppBackground = (
  rawPayload: unknown,
  apiBase = DEFAULT_API_BASE
): ResolvedAppBackground => {
  if (!isRecord(rawPayload)) {
    return { ...DEFAULT_APP_BACKGROUND, fallbackReason: 'missing-image' }
  }

  const nested = hasNestedCandidates(rawPayload)
  const legacySource = normalizeSource(rawPayload.source) || 'plugin'
  const order = nested ? buildSourceOrder(rawPayload) : [legacySource]
  let fallbackReason: AppBackgroundFallbackReason = 'disabled'

  for (const source of order) {
    const candidate = nested ? getNestedCandidate(rawPayload, source) : rawPayload
    if (!candidate) continue

    const resolved = resolveCandidate(source, candidate, rawPayload, apiBase)
    if (typeof resolved !== 'string') return resolved
    if (resolved === 'unsafe-url') fallbackReason = resolved
    else if (fallbackReason !== 'unsafe-url' && resolved === 'missing-image')
      fallbackReason = resolved
  }

  return { ...DEFAULT_APP_BACKGROUND, fallbackReason }
}

export const preloadBackgroundImage = async (url: string): Promise<boolean> => {
  if (!url || typeof Image === 'undefined') return false

  return await new Promise(resolve => {
    const image = new Image()
    image.decoding = 'async'
    image.onload = () => resolve(true)
    image.onerror = () => resolve(false)
    image.src = url
  })
}

export const resolveLoadableAppBackground = async (
  rawPayload: unknown,
  apiBase = DEFAULT_API_BASE,
  imageLoader: (url: string) => Promise<boolean> = preloadBackgroundImage
): Promise<ResolvedAppBackground> => {
  const resolved = resolveAppBackground(rawPayload, apiBase)
  if (!resolved.enabled) return resolved
  if (await imageLoader(resolved.imageUrl)) return resolved
  return { ...DEFAULT_APP_BACKGROUND, fallbackReason: 'image-load-failed' }
}
