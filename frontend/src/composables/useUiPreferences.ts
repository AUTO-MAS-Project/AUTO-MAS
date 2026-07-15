import type { GlobalConfig_UI } from '@/api'
import { readonly, ref } from 'vue'

const hideCloseButton = ref(false)

export function useUiPreferences() {
  const syncUiPreferences = (settings?: GlobalConfig_UI | null) => {
    hideCloseButton.value = settings?.IfHideCloseButton === true
  }

  return {
    hideCloseButton: readonly(hideCloseButton),
    syncUiPreferences,
  }
}
