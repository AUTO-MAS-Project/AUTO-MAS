import { defineStore } from 'pinia'
import { ref } from 'vue'
import { getConfig, saveConfig } from '@/utils/config'
import {
  DEFAULT_HOME_SATELLITE_STYLE,
  normalizeHomeSatelliteStyle,
  type HomeSatelliteStyle,
} from '@/types/homeSatellite'

export const useHomeSatelliteStore = defineStore('home-satellite', () => {
  const style = ref<HomeSatelliteStyle>(DEFAULT_HOME_SATELLITE_STYLE)
  const initialized = ref(false)
  const saving = ref(false)
  let loadPromise: Promise<void> | null = null

  const load = async (): Promise<void> => {
    if (initialized.value) {
      return
    }

    if (loadPromise) {
      return loadPromise
    }

    const pendingLoad = (async () => {
      try {
        const config = await getConfig()
        style.value = normalizeHomeSatelliteStyle(config.homeSatelliteStyle)
      } catch {
        style.value = DEFAULT_HOME_SATELLITE_STYLE
      } finally {
        initialized.value = true
        loadPromise = null
      }
    })()

    loadPromise = pendingLoad
    return pendingLoad
  }

  const setStyle = async (nextStyle: HomeSatelliteStyle): Promise<void> => {
    await load()

    const normalizedStyle = normalizeHomeSatelliteStyle(nextStyle)
    if (saving.value || normalizedStyle === style.value) {
      return
    }

    const previousStyle = style.value
    saving.value = true
    style.value = normalizedStyle

    try {
      await saveConfig({ homeSatelliteStyle: normalizedStyle })
    } catch (error) {
      style.value = previousStyle
      throw error
    } finally {
      saving.value = false
    }
  }

  return {
    style,
    initialized,
    saving,
    load,
    setStyle,
  }
})
