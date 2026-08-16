import { defineStore } from 'pinia'
import { ref } from 'vue'
import { getConfig, saveConfig } from '@/utils/config'
import {
  DEFAULT_CURSOR_EFFECT,
  normalizeCursorEffect,
  type CursorEffect,
} from '@/types/cursorEffect'

export const useCursorEffectStore = defineStore('cursor-effect', () => {
  const effect = ref<CursorEffect>(DEFAULT_CURSOR_EFFECT)
  const initialized = ref(false)
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
        effect.value = normalizeCursorEffect(config.cursorEffect)
      } catch {
        effect.value = DEFAULT_CURSOR_EFFECT
      } finally {
        initialized.value = true
        loadPromise = null
      }
    })()

    loadPromise = pendingLoad
    return pendingLoad
  }

  const setEffect = async (nextEffect: CursorEffect): Promise<void> => {
    await load()

    const normalizedEffect = normalizeCursorEffect(nextEffect)
    if (normalizedEffect === effect.value) {
      return
    }

    const previousEffect = effect.value
    effect.value = normalizedEffect

    try {
      await saveConfig({ cursorEffect: normalizedEffect })
    } catch (error) {
      effect.value = previousEffect
      throw error
    }
  }

  return {
    effect,
    initialized,
    load,
    setEffect,
  }
})
