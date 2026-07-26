import { OpenAPI } from '@/api'
import {
  DEFAULT_APP_BACKGROUND,
  DEFAULT_BACKGROUND_SETTINGS,
  clearUserBackgroundImage,
  clearUserBackgroundSettings,
  fileToDataUrl,
  loadUserBackgroundSettingsWithImage,
  resolveLoadableAppBackground,
  saveUserBackgroundImage,
  saveUserBackgroundSettings,
  validateImageFile,
  type AppBackgroundSettings,
  type AppBackgroundSource,
  type ResolvedAppBackground,
} from '@/theme/background'
import { authenticatedApiFetch } from '@/utils/httpSecurity'
import { computed, reactive, ref, watch } from 'vue'

interface AppBackgroundResponse {
  code?: number
  status?: string
  message?: string
  [key: string]: unknown
}

const logger = window.electronAPI.getLogger('应用背景')
const background = ref<ResolvedAppBackground>({ ...DEFAULT_APP_BACKGROUND })
const loaded = ref(false)
const userSettings = reactive<AppBackgroundSettings>({ ...DEFAULT_BACKGROUND_SETTINGS })
let loadGeneration = 0
let initialized = false

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

const syncUserSettings = (settings: Partial<AppBackgroundSettings>) => {
  Object.assign(userSettings, settings)
  saveUserBackgroundSettings(userSettings)
}

const applyResolvedToCssVars = (resolved: ResolvedAppBackground) => {
  background.value = resolved
}

export function useAppBackground() {
  const enabled = computed(() => background.value.enabled)
  const source = computed(() => background.value.source)
  const fallbackReason = computed(() => background.value.fallbackReason)
  const isUserSource = computed(() => userSettings.source === 'user')

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

  const cardBackgroundStyle = computed(() => ({
    backgroundColor: `color-mix(in srgb, var(--v6-color-surface) ${background.value.cardOpacity}%, transparent)`,
    backdropFilter: background.value.enabled ? 'var(--v6-backdrop-vibrancy)' : 'none',
  }))

  const panelBackgroundStyle = computed(() => ({
    backgroundColor: `color-mix(in srgb, var(--v6-color-surface) ${background.value.panelOpacity}%, transparent)`,
    backdropFilter: background.value.enabled ? 'var(--v6-backdrop-vibrancy)' : 'none',
  }))

  const siderBackgroundStyle = computed(() => ({
    backgroundColor: `color-mix(in srgb, var(--v6-color-sidebar) ${background.value.siderOpacity}%, transparent)`,
    backdropFilter: background.value.enabled ? 'var(--v6-backdrop-vibrancy)' : 'none',
  }))

  const loadBackground = async () => {
    const generation = ++loadGeneration

    try {
      const savedUser = await loadUserBackgroundSettingsWithImage()
      if (savedUser) {
        Object.assign(userSettings, savedUser)
      }

      if (userSettings.enabled && userSettings.source === 'user' && userSettings.imageDataUrl) {
        if (generation !== loadGeneration) return
        const resolved: ResolvedAppBackground = {
          ...userSettings,
          imageUrl: userSettings.imageDataUrl,
          fallbackReason: 'none',
        }
        applyResolvedToCssVars(resolved)
        if (generation === loadGeneration) loaded.value = true
        return
      }

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

      const resolved = await resolveLoadableAppBackground(payload, apiBase, userSettings)
      if (generation !== loadGeneration) return

      applyResolvedToCssVars(resolved)
      if (resolved.fallbackReason === 'unsafe-url') {
        logger.warn('背景服务返回了不安全的资源地址，已回退到默认背景')
      } else if (resolved.fallbackReason === 'image-load-failed') {
        logger.warn('背景图片无法加载或解码，已回退到默认背景')
      }
    } catch (error) {
      if (generation !== loadGeneration) return

      if (userSettings.enabled && userSettings.source === 'user' && userSettings.imageDataUrl) {
        const resolved: ResolvedAppBackground = {
          ...userSettings,
          imageUrl: userSettings.imageDataUrl,
          fallbackReason: 'none',
        }
        applyResolvedToCssVars(resolved)
      } else {
        const message = error instanceof Error ? error.message : String(error)
        applyResolvedToCssVars({ ...DEFAULT_APP_BACKGROUND })
        logger.warn(`加载应用背景失败，已回退到默认背景: ${message}`)
      }
    } finally {
      if (generation === loadGeneration) loaded.value = true
      initialized = true
    }
  }

  const selectLocalImage = async (file: File): Promise<{ success: boolean; reason?: string }> => {
    const validation = validateImageFile(file)
    if (!validation.valid) {
      return { success: false, reason: validation.reason }
    }

    try {
      const dataUrl = await fileToDataUrl(file)
      const saveResult = await saveUserBackgroundImage(dataUrl)
      if (!saveResult.success) {
        return { success: false, reason: saveResult.reason }
      }

      const settingsForStorage: Partial<AppBackgroundSettings> = {
        enabled: true,
        source: 'user',
      }
      syncUserSettings(settingsForStorage)
      userSettings.imageDataUrl = dataUrl

      const resolved: ResolvedAppBackground = {
        ...userSettings,
        imageUrl: dataUrl,
        fallbackReason: 'none',
      }
      applyResolvedToCssVars(resolved)
      return { success: true }
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error)
      logger.error(`读取本地图片失败: ${message}`)
      return { success: false, reason: '读取图片文件失败' }
    }
  }

  const clearBackground = () => {
    syncUserSettings({
      enabled: false,
      source: 'default',
    })
    userSettings.imageDataUrl = undefined
    void clearUserBackgroundImage()
    clearUserBackgroundSettings()
    Object.assign(userSettings, { ...DEFAULT_BACKGROUND_SETTINGS })
    applyResolvedToCssVars({ ...DEFAULT_APP_BACKGROUND })
  }

  const setEnabled = (value: boolean) => {
    syncUserSettings({ enabled: value })
    if (!value) {
      applyResolvedToCssVars({ ...DEFAULT_APP_BACKGROUND })
    } else {
      void loadBackground()
    }
  }

  const setSource = (source: AppBackgroundSource) => {
    syncUserSettings({ source })
    if (source === 'default' || (source === 'user' && !userSettings.imageDataUrl)) {
      if (source === 'default') {
        applyResolvedToCssVars({ ...DEFAULT_APP_BACKGROUND, enabled: userSettings.enabled })
      }
    } else {
      void loadBackground()
    }
  }

  const setBlur = (value: number) => {
    const blurPx = Math.max(0, Math.min(40, value))
    syncUserSettings({ blurPx })
    background.value = { ...background.value, blurPx }
  }

  const setBrightness = (value: number) => {
    const brightness = Math.max(50, Math.min(150, value))
    syncUserSettings({ brightness })
    background.value = { ...background.value, brightness }
  }

  const setOpacity = (value: number) => {
    const opacity = Math.max(0, Math.min(100, value))
    syncUserSettings({ opacity })
    background.value = { ...background.value, opacity }
  }

  const setOverlayOpacity = (value: number) => {
    const overlayOpacity = Math.max(0, Math.min(90, value))
    syncUserSettings({ overlayOpacity })
    background.value = { ...background.value, overlayOpacity }
  }

  const setCardOpacity = (value: number) => {
    const cardOpacity = Math.max(0, Math.min(100, value))
    syncUserSettings({ cardOpacity })
    background.value = { ...background.value, cardOpacity }
  }

  const setPosition = (position: AppBackgroundSettings['position']) => {
    syncUserSettings({ position })
    background.value = { ...background.value, position }
  }

  const setFit = (fit: AppBackgroundSettings['fit']) => {
    syncUserSettings({ fit })
    background.value = { ...background.value, fit }
  }

  const resetSettings = () => {
    Object.assign(userSettings, { ...DEFAULT_BACKGROUND_SETTINGS })
    userSettings.imageDataUrl = undefined
    void clearUserBackgroundImage()
    clearUserBackgroundSettings()
    void loadBackground()
  }

  if (!initialized) {
    void loadBackground()
  }

  watch(
    () => [
      userSettings.blurPx,
      userSettings.brightness,
      userSettings.opacity,
      userSettings.overlayOpacity,
      userSettings.cardOpacity,
      userSettings.position,
      userSettings.fit,
    ],
    () => {
      if (initialized && background.value.enabled) {
        background.value = {
          ...background.value,
          blurPx: userSettings.blurPx,
          brightness: userSettings.brightness,
          opacity: userSettings.opacity,
          overlayOpacity: userSettings.overlayOpacity,
          cardOpacity: userSettings.cardOpacity,
          panelOpacity: userSettings.panelOpacity,
          elevatedOpacity: userSettings.elevatedOpacity,
          siderOpacity: userSettings.siderOpacity,
          position: userSettings.position,
          fit: userSettings.fit,
        }
      }
    },
    { deep: true }
  )

  return {
    background,
    userSettings: computed(() => userSettings),
    enabled,
    source,
    fallbackReason,
    isUserSource,
    cssVars,
    cardBackgroundStyle,
    panelBackgroundStyle,
    siderBackgroundStyle,
    loaded,
    loadBackground,
    selectLocalImage,
    clearBackground,
    setEnabled,
    setSource,
    setBlur,
    setBrightness,
    setOpacity,
    setOverlayOpacity,
    setCardOpacity,
    setPosition,
    setFit,
    resetSettings,
  }
}
