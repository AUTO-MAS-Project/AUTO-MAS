import { computed, readonly, ref } from 'vue'
import { beginAnalyticsOperation } from '@/utils/analytics'
import { getConfig, saveConfig } from '@/utils/config'
import {
  readAppClosePreferences,
  updateAppClosePreferences,
  type AppCloseAction,
  type AppClosePreferences,
} from '@/utils/appClosePreferences'

const logger = window.electronAPI.getLogger('关闭应用设置')
const preferences = ref<AppClosePreferences>({ confirmBeforeClose: true, lastAction: 'quit' })
const loaded = ref(false)
const pendingSaves = ref(0)
let loadPromise: Promise<void> | null = null

async function load(): Promise<void> {
  if (loaded.value) return
  if (loadPromise) return loadPromise

  loadPromise = (async () => {
    try {
      preferences.value = readAppClosePreferences(await getConfig())
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.warn(`读取关闭应用设置失败: ${errorMsg}`)
      preferences.value = { confirmBeforeClose: true, lastAction: 'quit' }
    } finally {
      loaded.value = true
      loadPromise = null
    }
  })()

  return loadPromise
}

async function save(next: AppClosePreferences): Promise<void> {
  const current = preferences.value
  if (
    current.confirmBeforeClose === next.confirmBeforeClose &&
    current.lastAction === next.lastAction
  ) {
    return
  }

  const confirmationChanged = current.confirmBeforeClose !== next.confirmBeforeClose
  const analytics = confirmationChanged ? beginAnalyticsOperation('settings_change_finished') : null
  preferences.value = next
  pendingSaves.value += 1

  try {
    await saveConfig({
      confirmBeforeClose: next.confirmBeforeClose,
      lastCloseAction: next.lastAction,
    })
    analytics?.finish({
      setting_kind: 'close',
      setting_key: 'close_confirmation',
      value_kind: next.confirmBeforeClose ? 'enabled' : 'disabled',
      outcome: 'success',
    })
  } catch (error) {
    if (preferences.value === next) preferences.value = current
    analytics?.finish({
      setting_kind: 'close',
      setting_key: 'close_confirmation',
      value_kind: next.confirmBeforeClose ? 'enabled' : 'disabled',
      outcome: 'failure',
    })
    throw error
  } finally {
    pendingSaves.value -= 1
  }
}

async function setConfirmationEnabled(enabled: boolean): Promise<void> {
  await load()
  if (preferences.value.confirmBeforeClose === enabled) return
  await save({ ...preferences.value, confirmBeforeClose: enabled })
}

async function chooseAction(action: AppCloseAction, remember: boolean): Promise<void> {
  await load()
  await save(updateAppClosePreferences(preferences.value, action, remember))
}

export function useAppClosePreferences() {
  return {
    confirmBeforeClose: computed(() => preferences.value.confirmBeforeClose),
    lastAction: computed(() => preferences.value.lastAction),
    loaded: readonly(loaded),
    saving: computed(() => pendingSaves.value > 0),
    load,
    setConfirmationEnabled,
    chooseAction,
  }
}
