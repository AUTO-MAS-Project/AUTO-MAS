import { defineStore } from 'pinia'
import { ref } from 'vue'
import { getConfig, saveConfig } from '@/utils/config'
import {
  DEFAULT_PRESS_SOUND_ENABLED,
  DEFAULT_PRESS_SOUND_PRESET,
  DEFAULT_PRESS_SOUND_VOLUME,
  normalizePressSoundPreset,
  normalizePressSoundVolume,
  type PressSoundPreset,
} from '@/types/pressSound'

/** 主页中心图标按压音效的设置：开关、音效种类（内置或自定义文件）、音量 */
export const usePressSoundStore = defineStore('press-sound', () => {
  const enabled = ref(DEFAULT_PRESS_SOUND_ENABLED)
  const preset = ref<PressSoundPreset>(DEFAULT_PRESS_SOUND_PRESET)
  const volume = ref(DEFAULT_PRESS_SOUND_VOLUME)
  const customPath = ref('')
  const customName = ref('')
  const saving = ref(false)
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
        enabled.value = config.pressSoundEnabled ?? DEFAULT_PRESS_SOUND_ENABLED
        preset.value = normalizePressSoundPreset(config.pressSoundPreset)
        volume.value = normalizePressSoundVolume(config.pressSoundVolume)
        customPath.value = config.pressSoundCustomPath ?? ''
        customName.value = config.pressSoundCustomName ?? ''
      } catch {
        enabled.value = DEFAULT_PRESS_SOUND_ENABLED
        preset.value = DEFAULT_PRESS_SOUND_PRESET
        volume.value = DEFAULT_PRESS_SOUND_VOLUME
        customPath.value = ''
        customName.value = ''
      } finally {
        initialized.value = true
        loadPromise = null
      }
    })()

    loadPromise = pendingLoad
    return pendingLoad
  }

  /** persist 排成一条链：并发调用时后一次等前一次落盘完再开始 */
  let persistChain: Promise<void> = Promise.resolve()

  /**
   * 写盘；失败把内存值还原，避免界面显示的和保存的不一致。
   *
   * 之所以要串行：连着改两项时两次 persist 会并发跑，如果早的那次失败、晚的那次成功，
   * 早的那次回滚就会把晚的那次已经写进配置的值在内存里盖掉，界面从此和配置对不上。
   */
  const persist = (next: {
    enabled?: boolean
    preset?: PressSoundPreset
    volume?: number
    customPath?: string
    customName?: string
  }): Promise<void> => {
    const run = async (): Promise<void> => {
      await load()

      const previous = {
        enabled: enabled.value,
        preset: preset.value,
        volume: volume.value,
        customPath: customPath.value,
        customName: customName.value,
      }

      if (next.enabled !== undefined) {
        enabled.value = next.enabled
      }
      if (next.preset !== undefined) {
        preset.value = normalizePressSoundPreset(next.preset)
      }
      if (next.volume !== undefined) {
        volume.value = normalizePressSoundVolume(next.volume)
      }
      if (next.customPath !== undefined) {
        customPath.value = next.customPath
      }
      if (next.customName !== undefined) {
        customName.value = next.customName
      }

      try {
        saving.value = true
        await saveConfig({
          pressSoundEnabled: enabled.value,
          pressSoundPreset: preset.value,
          pressSoundVolume: volume.value,
          pressSoundCustomPath: customPath.value,
          pressSoundCustomName: customName.value,
        })
      } catch (error) {
        enabled.value = previous.enabled
        preset.value = previous.preset
        volume.value = previous.volume
        customPath.value = previous.customPath
        customName.value = previous.customName
        throw error
      } finally {
        saving.value = false
      }
    }

    // 前一次不管成功失败都要接着跑下一次，所以 then 的两条分支都是 run
    const queued = persistChain.then(run, run)
    // 链本身不能被某次失败打断，错误交给调用方从 queued 上取
    persistChain = queued.catch(() => {})
    return queued
  }

  return {
    enabled,
    preset,
    volume,
    customPath,
    customName,
    saving,
    initialized,
    load,
    persist,
  }
})
