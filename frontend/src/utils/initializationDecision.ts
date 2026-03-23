import {
  decideInitializationMode,
  type InitializationDecisionMode,
} from '@/utils/initializationPolicy'

export interface InitializationDecision {
  mode: InitializationDecisionMode
  currentVersion: string
  savedVersion: string | null
  autoUpdateEnabled: boolean
  forceBackendUpdate: boolean
}

const logger = window.electronAPI.getLogger('初始化决策')

/**
 * dev 模式是否进入初始化：
 * - 默认 false（dev 不进入初始化）
 * - 仅当 VITE_DEV_ENTER_INITIALIZATION 严格等于 "true" 时进入初始化
 */
export function shouldEnterInitializationInDev(): boolean {
  return (import.meta as any).env?.VITE_DEV_ENTER_INITIALIZATION === 'true'
}

export async function getInitializationDecision(): Promise<InitializationDecision> {
  const api = window.electronAPI as any
  const currentVersion = import.meta.env.VITE_APP_VERSION
  const forceBackendUpdate = sessionStorage.getItem('forceBackendUpdate') === 'true'
  const disableSkip = sessionStorage.getItem('disableInitializationSkip') === 'true'

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

  const mode = decideInitializationMode({
    isDev: import.meta.env.DEV,
    devEnterInitialization: shouldEnterInitializationInDev(),
    currentVersion,
    savedVersion,
    autoUpdateEnabled,
    forceBackendUpdate,
    disableSkip,
  })

  return {
    mode,
    currentVersion,
    savedVersion,
    autoUpdateEnabled,
    forceBackendUpdate,
  }
}
