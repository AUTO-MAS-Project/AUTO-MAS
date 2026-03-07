export type InitializationDecisionMode = 'skip-home' | 'full-init' | 'force-backend-update'

export interface InitializationDecision {
  mode: InitializationDecisionMode
  currentVersion: string
  savedVersion: string | null
  autoUpdateEnabled: boolean
  forceBackendUpdate: boolean
}

const logger = window.electronAPI.getLogger('初始化决策')

export async function getInitializationDecision(): Promise<InitializationDecision> {
  const api = window.electronAPI as any
  const currentVersion = import.meta.env.VITE_APP_VERSION
  const forceBackendUpdate = sessionStorage.getItem('forceBackendUpdate') === 'true'
  const disableSkip = sessionStorage.getItem('disableInitializationSkip') === 'true'

  if (forceBackendUpdate) {
    return {
      mode: 'force-backend-update',
      currentVersion,
      savedVersion: null,
      autoUpdateEnabled: false,
      forceBackendUpdate,
    }
  }

  if (disableSkip) {
    return {
      mode: 'full-init',
      currentVersion,
      savedVersion: null,
      autoUpdateEnabled: false,
      forceBackendUpdate,
    }
  }

  if (import.meta.env.DEV) {
    return {
      mode: 'skip-home',
      currentVersion,
      savedVersion: currentVersion,
      autoUpdateEnabled: false,
      forceBackendUpdate,
    }
  }

  let autoUpdateEnabled = false
  try {
    const config = await api.loadConfig?.()
    autoUpdateEnabled = config?.Update?.IfAutoUpdate ?? false
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.warn(`读取自动更新配置失败，回退为完整初始化: ${errorMsg}`)
  }

  let savedVersion: string | null = null
  try {
    savedVersion = await api.getInitializedVersion?.()
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.warn(`读取初始化版本失败，回退为完整初始化: ${errorMsg}`)
  }

  if (!autoUpdateEnabled && savedVersion === currentVersion) {
    return {
      mode: 'skip-home',
      currentVersion,
      savedVersion,
      autoUpdateEnabled,
      forceBackendUpdate,
    }
  }

  return {
    mode: 'full-init',
    currentVersion,
    savedVersion,
    autoUpdateEnabled,
    forceBackendUpdate,
  }
}
