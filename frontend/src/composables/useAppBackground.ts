import { OpenAPI } from '@/api'
import {
  DEFAULT_APP_BACKGROUND,
  resolveLoadableAppBackground,
  type ResolvedAppBackground,
} from '@/theme/background'
import { authenticatedApiFetch } from '@/utils/httpSecurity'
import { computed, ref } from 'vue'

interface AppBackgroundResponse {
  code?: number
  status?: string
  message?: string
  [key: string]: unknown
}

const logger = window.electronAPI.getLogger('应用背景')
const background = ref<ResolvedAppBackground>({ ...DEFAULT_APP_BACKGROUND })
const loaded = ref(false)
let loadGeneration = 0

const getApiBase = async () => {
  if (OpenAPI.BASE) return OpenAPI.BASE

  try {
    if (window.electronAPI?.getApiEndpoint) {
      const endpoint = await window.electronAPI.getApiEndpoint('local')
      OpenAPI.BASE = endpoint
      return endpoint
    }
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error)
    logger.warn(`获取背景服务端点失败，使用本地默认端点: ${message}`)
  }

  OpenAPI.BASE = 'http://127.0.0.1:36163'
  return OpenAPI.BASE
}

const toBackgroundEndpoint = (apiBase: string) =>
  `${apiBase.replace(/\/+$/, '')}/api/plugins/frontend/background`

export function useAppBackground() {
  const enabled = computed(() => background.value.enabled)
  const source = computed(() => background.value.source)
  const fallbackReason = computed(() => background.value.fallbackReason)
  const cssVars = computed(() => ({
    '--app-background-image': background.value.imageUrl
      ? `url("${background.value.imageUrl}")`
      : 'none',
    '--app-background-blur': `${background.value.blurPx}px`,
    '--app-background-brightness': `${background.value.brightness}%`,
    '--app-background-opacity': `${background.value.opacity / 100}`,
    '--app-background-overlay-opacity': `${background.value.overlayOpacity / 100}`,
    '--app-background-card-opacity': `${background.value.cardOpacity}%`,
    '--app-background-panel-opacity': `${background.value.panelOpacity}%`,
    '--app-background-elevated-opacity': `${background.value.elevatedOpacity}%`,
    '--app-background-sider-opacity': `${background.value.siderOpacity}%`,
    '--app-background-position': background.value.position,
    '--app-background-size': background.value.fit,
  }))

  const loadBackground = async () => {
    const generation = ++loadGeneration

    try {
      const apiBase = await getApiBase()
      const response = await authenticatedApiFetch(toBackgroundEndpoint(apiBase), {
        headers: { Accept: 'application/json' },
        cache: 'no-store',
      })
      const payload = (await response.json()) as AppBackgroundResponse

      if (
        !response.ok ||
        payload.status === 'error' ||
        (payload.code !== undefined && payload.code !== 200)
      ) {
        throw new Error(payload.message || `HTTP ${response.status}`)
      }

      const resolved = await resolveLoadableAppBackground(payload, apiBase)
      if (generation !== loadGeneration) return

      background.value = resolved
      if (resolved.fallbackReason === 'unsafe-url') {
        logger.warn('背景服务返回了不安全的资源地址，已回退到默认背景')
      } else if (resolved.fallbackReason === 'image-load-failed') {
        logger.warn('背景图片无法加载或解码，已回退到默认背景')
      }
    } catch (error) {
      if (generation !== loadGeneration) return

      const message = error instanceof Error ? error.message : String(error)
      background.value = { ...DEFAULT_APP_BACKGROUND }
      logger.warn(`加载应用背景失败，已回退到默认背景: ${message}`)
    } finally {
      if (generation === loadGeneration) loaded.value = true
    }
  }

  return {
    background,
    enabled,
    source,
    fallbackReason,
    cssVars,
    loaded,
    loadBackground,
  }
}
