export interface DevInitializationOptions {
  isDev: boolean
  devEnterInitialization: boolean
}

export interface InitializationDecisionInput extends DevInitializationOptions {
  currentVersion: string
  savedVersion: string | null
  autoUpdateEnabled: boolean
  forceBackendUpdate: boolean
  disableSkip: boolean
}

export type InitializationDecisionMode = 'skip-home' | 'full-init' | 'force-backend-update'

export function shouldBypassInitializationGuardInDev({
  isDev,
  devEnterInitialization,
}: DevInitializationOptions): boolean {
  return isDev && !devEnterInitialization
}

export function shouldSkipInitializationViewInDev(
  options: DevInitializationOptions
): boolean {
  return shouldBypassInitializationGuardInDev(options)
}

export function decideInitializationMode(
  input: InitializationDecisionInput
): InitializationDecisionMode {
  if (input.forceBackendUpdate) {
    return 'force-backend-update'
  }

  if (input.disableSkip) {
    return 'full-init'
  }

  if (shouldBypassInitializationGuardInDev(input)) {
    return 'skip-home'
  }

  if (!input.autoUpdateEnabled && input.savedVersion === input.currentVersion) {
    return 'skip-home'
  }

  return 'full-init'
}
