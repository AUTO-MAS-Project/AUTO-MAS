/**
 * App Shell 启动状态类型
 */
export type AppStartupStatus =
  | 'initializing'
  | 'backend-starting'
  | 'connected'
  | 'offline'
  | 'reconnecting'
  | 'timeout'
  | 'failed'
  | 'closing'

/**
 * 启动轨道的真实阶段。阶段由启动入口显式推进，避免用虚构百分比掩盖等待状态。
 */
export type AppStartupStage = 'renderer' | 'runtime' | 'backend' | 'connection' | 'ready'

export interface AppStartupState {
  status: AppStartupStatus
  stage?: AppStartupStage
  message: string
  detail?: string
  canRetry: boolean
  canCopyDiagnostics: boolean
  canExit: boolean
  canOpenLogs?: boolean
}

export interface BackendStartupOverlayProps {
  visible: boolean
  state: AppStartupState
}
