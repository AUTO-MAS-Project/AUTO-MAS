export type HotUpdatePhase =
  | 'download'
  | 'stopping'
  | 'installing'
  | 'starting'
  | 'connecting'
  | 'completed'
export type HotUpdateRepair = 'dependencies-sync' | 'dependencies-rebuild' | 'runtime-repair'

/** 编排及通知记录；安装事务仍完全归 Runtime 所有。 */
export interface HotUpdateRecord {
  operationId: string
  baseCommit: string | null
  targetCommit: string | null
  version?: string
  phase: HotUpdatePhase
  result: 'success' | 'failed' | 'cancelled' | null
  error?: string
  code?: string
  retryable?: boolean
  backendAvailable?: boolean
  remediation?: string[]
  logs?: string
  notified: boolean
  notifiedFailure?: string
  timestamp: string
}

export interface HotUpdateHooks {
  onPhase: (phase: HotUpdatePhase) => void
  rendererReady: () => Promise<boolean>
  isClosing: () => boolean
}
