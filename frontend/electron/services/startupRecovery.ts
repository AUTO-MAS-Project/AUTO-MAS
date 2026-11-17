import type { RuntimeRunResult } from './runtime/client'
import type { RuntimeRemediation } from './runtime/protocol'

/** 保留失败边界的事实；进程退出只能由本机 RuntimeClient 确认。 */
export interface StartupFailureContext {
  command?: string
  processExited?: boolean
  stage?: string
  failureKind?: string
  windowsError?: number
  businessDeferred?: boolean
  activationRequested?: true
}

export function runtimeFailureContext(result: RuntimeRunResult): StartupFailureContext {
  const primary = result.errors.at(-1)
  const details = { ...result.result.details, ...primary?.details }
  return {
    command: result.hello.command,
    processExited: true,
    stage: primary?.stage ?? result.result.stage,
    failureKind: typeof details.failureKind === 'string' ? details.failureKind : undefined,
    windowsError: typeof details.windowsError === 'number' ? details.windowsError : undefined,
    businessDeferred: details.businessDeferred === true,
  }
}

interface StartupFailure {
  code?: string
  retryable?: boolean
  remediation?: RuntimeRemediation[]
  runtimeFailure?: StartupFailureContext
  networkUnavailable?: true
}

/** 只重放已有准备与启动操作，不将普通重试升级为重建或权限修复。 */
export function canRetryStartup(result: StartupFailure): boolean {
  if (
    !result.retryable ||
    result.runtimeFailure?.activationRequested ||
    result.runtimeFailure?.processExited === false
  )
    return false
  const context = result.runtimeFailure
  if (context?.failureKind === 'start_failed' && [5, 740].includes(context.windowsError ?? 0)) {
    return false
  }
  switch (result.code) {
    case 'RUNTIME_LATEST_UNAVAILABLE':
    case 'RUNTIME_BINARY_DOWNLOAD_FAILED':
      return result.networkUnavailable === true
    case 'RUNTIME_HANDSHAKE_TIMEOUT':
      return ['workspace check', 'bootstrap', 'environment ensure', 'dependencies sync'].includes(
        context?.command ?? ''
      )
    case 'UV_EXEC_FAILED':
      return (
        context?.stage === 'uv.verify' &&
        ['process_isolation_failed', 'output_read_failed'].includes(context.failureKind ?? '')
      )
    case 'NETWORK_UNAVAILABLE':
    case 'MIRROR_EXHAUSTED':
    case 'UV_DOWNLOAD_FAILED':
    case 'PYTHON_INSTALL_FAILED':
    case 'DEPENDENCY_SYNC_FAILED':
      return (
        result.remediation?.some(value =>
          ['retry', 'retry-other-mirror', 'retry-sync'].includes(value)
        ) === true
      )
    case 'BACKEND_HEALTH_TIMEOUT':
    case 'BACKEND_EXITED_BEFORE_READY':
    case 'BACKEND_SPAWN_FAILED':
      return context?.businessDeferred === true
    default:
      return false
  }
}
