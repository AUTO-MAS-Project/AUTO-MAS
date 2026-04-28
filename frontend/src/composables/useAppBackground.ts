import { computed, ref } from 'vue'
import { OpenAPI } from '@/api'

interface AppBackgroundResponse {
  code?: number
  status?: string
  message?: string
  enabled?: boolean
  image_url?: string | null
  blur_px?: number
  brightness?: number
  opacity?: number
  overlay_opacity?: number
  card_opacity?: number
  position?: string
  fit?: string
}

const background = ref<AppBackgroundResponse>({
  enabled: false,
})
const loaded = ref(false)

const toPercent = (value: unknown, fallback: number) => {
  const parsed = Number(value)
  return Number.isFinite(parsed) ? Math.max(0, Math.min(160, parsed)) : fallback
}

const toPx = (value: unknown, fallback: number) => {
  const parsed = Number(value)
  return Number.isFinite(parsed) ? Math.max(0, Math.min(40, parsed)) : fallback
}

const toPosition = (value: unknown) => {
  if (value === 'top') {
    return 'center top'
  }
  if (value === 'bottom') {
    return 'center bottom'
  }
  return 'center center'
}

const toFit = (value: unknown) => (value === 'contain' ? 'contain' : 'cover')

const buildUrl = (url?: string | null) => {
  if (!url) {
    return ''
  }
  if (/^https?:\/\//i.test(url)) {
    return url
  }
  const base = OpenAPI.BASE || ''
  return `${base}${url.startsWith('/') ? url : `/${url}`}`
}

const getApiBase = async () => {
  if (OpenAPI.BASE) {
    return OpenAPI.BASE
  }
  try {
    if (window.electronAPI?.getApiEndpoint) {
      const endpoint = await window.electronAPI.getApiEndpoint('local')
      OpenAPI.BASE = endpoint
      return endpoint
    }
  } catch {
    // fall through to default local endpoint
  }
  OpenAPI.BASE = 'http://localhost:36163'
  return OpenAPI.BASE
}

export function useAppBackground() {
  const enabled = computed(() => Boolean(background.value.enabled && background.value.image_url))
  const imageUrl = computed(() => buildUrl(background.value.image_url))
  const cssVars = computed(() => ({
    '--app-background-image': imageUrl.value ? `url("${imageUrl.value}")` : 'none',
    '--app-background-blur': `${toPx(background.value.blur_px, 0)}px`,
    '--app-background-brightness': `${toPercent(background.value.brightness, 100)}%`,
    '--app-background-opacity': `${toPercent(background.value.opacity, 100) / 100}`,
    '--app-background-overlay-opacity': `${toPercent(background.value.overlay_opacity, 0) / 100}`,
    '--app-background-card-opacity': `${toPercent(background.value.card_opacity, 92)}%`,
    '--app-background-position': toPosition(background.value.position),
    '--app-background-size': toFit(background.value.fit),
  }))

  const loadBackground = async () => {
    try {
      const base = await getApiBase()
      const response = await fetch(`${base}/api/plugins/frontend/background`)
      const data = (await response.json()) as AppBackgroundResponse
      if (!response.ok || data.code === 500 || data.status === 'error') {
        background.value = { enabled: false }
        return
      }
      background.value = data
    } catch {
      background.value = { enabled: false }
    } finally {
      loaded.value = true
    }
  }

  return {
    background,
    enabled,
    cssVars,
    loaded,
    loadBackground,
  }
}
