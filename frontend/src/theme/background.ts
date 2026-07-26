export type AppBackgroundSource = 'default' | 'user' | 'plugin'
export type AppBackgroundFallbackReason =
  | 'none'
  | 'disabled'
  | 'missing-image'
  | 'unsafe-url'
  | 'image-load-failed'
  | 'local-file-error'
  | 'storage-quota-exceeded'

export interface AppBackgroundSettings {
  enabled: boolean
  source: AppBackgroundSource
  imageDataUrl?: string
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
}

export interface ResolvedAppBackground extends AppBackgroundSettings {
  imageUrl: string
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

const ALLOWED_IMAGE_TYPES = ['image/png', 'image/jpeg', 'image/webp', 'image/gif', 'image/bmp']
const MAX_IMAGE_SIZE_BYTES = 10 * 1024 * 1024

const USER_BACKGROUND_STORAGE_KEY = 'v6-user-background'
const USER_BACKGROUND_IDB_DB = 'auto-mas-v6'
const USER_BACKGROUND_IDB_STORE = 'background-images'
const USER_BACKGROUND_IDB_KEY = 'user-wallpaper'

export const DEFAULT_APP_BACKGROUND: ResolvedAppBackground = {
  source: 'default',
  enabled: false,
  imageUrl: '',
  imageDataUrl: undefined,
  blurPx: 0,
  brightness: 100,
  opacity: 100,
  overlayOpacity: 0,
  cardOpacity: 100,
  panelOpacity: 100,
  elevatedOpacity: 100,
  siderOpacity: 88,
  position: 'center center',
  fit: 'cover',
  fallbackReason: 'disabled',
}

export const DEFAULT_BACKGROUND_SETTINGS: AppBackgroundSettings = {
  enabled: false,
  source: 'default',
  blurPx: 8,
  brightness: 100,
  opacity: 70,
  overlayOpacity: 15,
  cardOpacity: 92,
  panelOpacity: 96,
  elevatedOpacity: 98,
  siderOpacity: 88,
  position: 'center center',
  fit: 'cover',
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
  if (isRecord(sources) && isRecord(sources[source])) return sources[source] as UnknownRecord

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

  if (raw.startsWith('data:image/')) {
    return raw
  }

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
  apiBase: string,
  userDataUrl?: string
): ResolvedAppBackground | AppBackgroundFallbackReason => {
  if (candidate.enabled === false) return 'disabled'

  let imageUrl = ''
  if (source === 'user' && userDataUrl) {
    imageUrl = userDataUrl
  } else {
    const imageValue = readValue(candidate, envelope, 'image_url', 'imageUrl')
    if (typeof imageValue !== 'string' || !imageValue.trim()) return 'missing-image'
    imageUrl = resolveSafeBackgroundUrl(imageValue, apiBase)
    if (!imageUrl) return 'unsafe-url'
  }

  const cardOpacity = toPercent(readValue(candidate, envelope, 'card_opacity', 'cardOpacity'), 92)

  return {
    source,
    enabled: true,
    imageUrl,
    imageDataUrl: source === 'user' ? userDataUrl : undefined,
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
  apiBase = DEFAULT_API_BASE,
  userSettings?: AppBackgroundSettings | null
): ResolvedAppBackground => {
  if (userSettings?.enabled && userSettings.source === 'user' && userSettings.imageDataUrl) {
    return {
      ...DEFAULT_BACKGROUND_SETTINGS,
      ...userSettings,
      imageUrl: userSettings.imageDataUrl,
      fallbackReason: 'none',
    }
  }

  if (!isRecord(rawPayload)) {
    return { ...DEFAULT_APP_BACKGROUND, fallbackReason: 'missing-image' }
  }

  const nested = hasNestedCandidates(rawPayload)
  const legacySource = normalizeSource(rawPayload.source) || 'plugin'
  const order = nested ? buildSourceOrder(rawPayload) : [legacySource]
  let fallbackReason: AppBackgroundFallbackReason = 'disabled'

  for (const source of order) {
    if (source === 'user' && userSettings?.enabled && userSettings.imageDataUrl) {
      return {
        ...DEFAULT_BACKGROUND_SETTINGS,
        ...userSettings,
        imageUrl: userSettings.imageDataUrl,
        fallbackReason: 'none',
      }
    }
    const candidate = nested ? getNestedCandidate(rawPayload, source) : rawPayload
    if (!candidate) continue

    const resolved = resolveCandidate(
      source,
      candidate,
      rawPayload,
      apiBase,
      userSettings?.imageDataUrl
    )
    if (typeof resolved !== 'string') return resolved
    if (resolved === 'unsafe-url') fallbackReason = resolved
    else if (fallbackReason !== 'unsafe-url' && resolved === 'missing-image')
      fallbackReason = resolved
  }

  return { ...DEFAULT_APP_BACKGROUND, fallbackReason }
}

export const preloadBackgroundImage = async (url: string): Promise<boolean> => {
  if (!url) return false
  if (url.startsWith('data:image/')) {
    return true
  }
  if (typeof Image === 'undefined') return false

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
  userSettings?: AppBackgroundSettings | null,
  imageLoader: (url: string) => Promise<boolean> = preloadBackgroundImage
): Promise<ResolvedAppBackground> => {
  const resolved = resolveAppBackground(rawPayload, apiBase, userSettings)
  if (!resolved.enabled) return resolved
  if (await imageLoader(resolved.imageUrl)) return resolved
  return { ...DEFAULT_APP_BACKGROUND, fallbackReason: 'image-load-failed' }
}

export const validateImageFile = (file: File): { valid: boolean; reason?: string } => {
  if (!ALLOWED_IMAGE_TYPES.includes(file.type)) {
    return { valid: false, reason: `不支持的图片格式: ${file.type}，请使用 PNG/JPEG/WebP/GIF/BMP` }
  }
  if (file.size > MAX_IMAGE_SIZE_BYTES) {
    return {
      valid: false,
      reason: `图片过大（${(file.size / 1024 / 1024).toFixed(1)}MB），最大支持 10MB`,
    }
  }
  return { valid: true }
}

export const fileToDataUrl = (file: File): Promise<string> => {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(reader.result as string)
    reader.onerror = () => reject(new Error('读取文件失败'))
    reader.readAsDataURL(file)
  })
}

function openBackgroundIDB(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    if (typeof indexedDB === 'undefined') {
      reject(new Error('IndexedDB unavailable'))
      return
    }
    const request = indexedDB.open(USER_BACKGROUND_IDB_DB, 1)
    request.onupgradeneeded = () => {
      const db = request.result
      if (!db.objectStoreNames.contains(USER_BACKGROUND_IDB_STORE)) {
        db.createObjectStore(USER_BACKGROUND_IDB_STORE)
      }
    }
    request.onsuccess = () => resolve(request.result)
    request.onerror = () => reject(request.error ?? new Error('IndexedDB open failed'))
  })
}

async function idbPut(key: string, value: string): Promise<void> {
  const db = await openBackgroundIDB()
  return new Promise((resolve, reject) => {
    const tx = db.transaction(USER_BACKGROUND_IDB_STORE, 'readwrite')
    const store = tx.objectStore(USER_BACKGROUND_IDB_STORE)
    const req = store.put(value, key)
    req.onsuccess = () => resolve()
    req.onerror = () => reject(req.error ?? new Error('IndexedDB put failed'))
    tx.oncomplete = () => db.close()
    tx.onerror = () => reject(tx.error ?? new Error('IndexedDB transaction failed'))
  })
}

async function idbGet(key: string): Promise<string | null> {
  const db = await openBackgroundIDB()
  return new Promise((resolve, reject) => {
    const tx = db.transaction(USER_BACKGROUND_IDB_STORE, 'readonly')
    const store = tx.objectStore(USER_BACKGROUND_IDB_STORE)
    const req = store.get(key)
    req.onsuccess = () => {
      const result = req.result
      resolve(typeof result === 'string' ? result : null)
    }
    req.onerror = () => reject(req.error ?? new Error('IndexedDB get failed'))
    tx.oncomplete = () => db.close()
  })
}

async function idbDelete(key: string): Promise<void> {
  const db = await openBackgroundIDB()
  return new Promise((resolve, reject) => {
    const tx = db.transaction(USER_BACKGROUND_IDB_STORE, 'readwrite')
    const store = tx.objectStore(USER_BACKGROUND_IDB_STORE)
    const req = store.delete(key)
    req.onsuccess = () => resolve()
    req.onerror = () => reject(req.error ?? new Error('IndexedDB delete failed'))
    tx.oncomplete = () => db.close()
  })
}

function settingsWithoutImageDataUrl(
  settings: AppBackgroundSettings
): Partial<AppBackgroundSettings> {
  const { imageDataUrl: _omit, ...rest } = settings
  return rest
}

function hasStoredUserImage(settings: AppBackgroundSettings | null): boolean {
  return !!(settings?.enabled && settings.source === 'user')
}

export const saveUserBackgroundSettings = (settings: AppBackgroundSettings): void => {
  try {
    const serializable = settingsWithoutImageDataUrl(settings)
    localStorage.setItem(USER_BACKGROUND_STORAGE_KEY, JSON.stringify(serializable))
  } catch {
    // localStorage unavailable or quota exceeded; ignore metadata persistence failure
  }
}

export const saveUserBackgroundImage = async (
  dataUrl: string
): Promise<{ success: boolean; reason?: string }> => {
  try {
    await idbPut(USER_BACKGROUND_IDB_KEY, dataUrl)
    return { success: true }
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error)
    const isQuota =
      message.includes('QuotaExceededError') ||
      message.includes('quota') ||
      message.includes('Quota')
    return {
      success: false,
      reason: isQuota ? 'storage-quota-exceeded' : 'local-file-error',
    }
  }
}

export const loadUserBackgroundSettings = (): AppBackgroundSettings | null => {
  try {
    const raw = localStorage.getItem(USER_BACKGROUND_STORAGE_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw) as Partial<AppBackgroundSettings>
    return {
      ...DEFAULT_BACKGROUND_SETTINGS,
      ...parsed,
    }
  } catch {
    return null
  }
}

export const loadUserBackgroundImage = async (): Promise<string | null> => {
  try {
    return await idbGet(USER_BACKGROUND_IDB_KEY)
  } catch {
    return null
  }
}

export const loadUserBackgroundSettingsWithImage =
  async (): Promise<AppBackgroundSettings | null> => {
    const settings = loadUserBackgroundSettings()
    if (!settings || !hasStoredUserImage(settings)) {
      return settings
    }
    const dataUrl = await loadUserBackgroundImage()
    if (dataUrl) {
      return { ...settings, imageDataUrl: dataUrl }
    }
    return { ...settings, enabled: false, source: 'default' }
  }

export const clearUserBackgroundSettings = (): void => {
  try {
    localStorage.removeItem(USER_BACKGROUND_STORAGE_KEY)
  } catch {
    // localStorage unavailable; ignore
  }
}

export const clearUserBackgroundImage = async (): Promise<void> => {
  try {
    await idbDelete(USER_BACKGROUND_IDB_KEY)
  } catch {
    // IndexedDB unavailable; ignore
  }
}
