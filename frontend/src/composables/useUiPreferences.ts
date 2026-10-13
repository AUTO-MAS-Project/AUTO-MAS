import type { SettingsViewModel } from '@/types/settings'
import { readonly, ref } from 'vue'

const hideCloseButton = ref(false)

export function useUiPreferences() {
  const syncUiPreferences = (settings?: SettingsViewModel['UI'] | null) => {
    hideCloseButton.value = settings?.IfHideCloseButton === true
  }

  return {
    hideCloseButton: readonly(hideCloseButton),
    syncUiPreferences,
  }
}
