export type AppCloseAction = 'quit' | 'tray'

export interface AppClosePreferences {
  confirmBeforeClose: boolean
  lastAction: AppCloseAction
}

interface StoredAppClosePreferences {
  confirmBeforeClose?: unknown
  lastCloseAction?: unknown
}

export function readAppClosePreferences(config: unknown): AppClosePreferences {
  const stored = config && typeof config === 'object' ? (config as StoredAppClosePreferences) : {}
  return {
    confirmBeforeClose: stored.confirmBeforeClose !== false,
    lastAction: stored.lastCloseAction === 'tray' ? 'tray' : 'quit',
  }
}

export function updateAppClosePreferences(
  current: AppClosePreferences,
  action: AppCloseAction,
  remember: boolean
): AppClosePreferences {
  return {
    confirmBeforeClose: remember ? false : current.confirmBeforeClose,
    lastAction: action,
  }
}
