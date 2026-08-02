export type InitializationDecisionMode = 'skip-home' | 'full-init' | 'force-backend-update'

// 预取缓存：main.ts 启动时就发起，路由守卫复用结果，避免重复 IPC
let _cachedDecision: Promise<InitializationDecision> | null = null

/**
 * 提前预取初始化决策，与 createApp 并行执行。
 * 路由守卫调用 getInitializationDecision() 时会复用该缓存。
 */
export function prefetchInitializationDecision(): Promise<InitializationDecision> {
  if (!_cachedDecision) {
    _cachedDecision = _fetchDecision()
  }
  return _cachedDecision
}

export interface InitializationDecision {
  mode: InitializationDecisionMode
  currentVersion: string
  savedVersion: string | null
  autoUpdateEnabled: boolean
  forceBackendUpdate: boolean
}

const logger = window.electronAPI.getLogger('初始化决策')

/**
 * 对外接口：复用预取缓存（若 prefetchInitializationDecision 已被调用则零延迟返回）。
 * 路由守卫里调用此函数即可——不再重复发 IPC。
 */
export function getInitializationDecision(): Promise<InitializationDecision> {
  const forceBackendUpdate = sessionStorage.getItem('forceBackendUpdate') === 'true'
  const disableSkip = sessionStorage.getItem('disableInitializationSkip') === 'true'
  if (forceBackendUpdate || disableSkip) {
    return _fetchDecision()
  }
  return prefetchInitializationDecision()
}

/**
 * 实际拉取逻辑（只执行一次）。
 * 内部将两个串行 IPC（loadConfig + getInitializedVersion）改为并行，节省约 20-40ms。
 */
async function _fetchDecision(): Promise<InitializationDecision> {
  const api = window.electronAPI
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
    // disableSkip 由会话状态驱动，不需要查版本，直接返回
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

  // 并行发两个 IPC，不再串行等待
  const [configResult, savedVersionResult] = await Promise.allSettled([
    api.loadConfig?.(),
    api.getInitializedVersion?.(),
  ])

  let autoUpdateEnabled = false
  if (configResult.status === 'fulfilled') {
    autoUpdateEnabled = configResult.value?.Update?.IfAutoUpdate ?? false
  } else {
    logger.warn(`读取自动更新配置失败，回退为完整初始化: ${configResult.reason}`)
  }

  let savedVersion: string | null = null
  if (savedVersionResult.status === 'fulfilled') {
    savedVersion = savedVersionResult.value ?? null
  } else {
    logger.warn(`读取初始化版本失败，回退为完整初始化: ${savedVersionResult.reason}`)
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
