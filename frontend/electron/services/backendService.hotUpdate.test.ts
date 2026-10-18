import { describe, expect, it, vi } from 'vite-plus/test'

vi.mock('electron', () => ({
  app: { getVersion: () => '5.7.0-beta.5', getPath: () => 'E:\\tmp', isPackaged: true },
  BrowserWindow: class {
    static getAllWindows() {
      return []
    }
  },
}))
vi.mock('./logger', () => ({
  getLogger: () => ({
    error: vi.fn(),
    warn: vi.fn(),
    info: vi.fn(),
    verbose: vi.fn(),
    debug: vi.fn(),
    silly: vi.fn(),
  }),
}))
vi.mock('./sentry', () => ({
  observeMainOperation: () => ({ end: vi.fn() }),
  recordMainCount: vi.fn(),
  recordMainDuration: vi.fn(),
}))

import { BackendService } from './backendService'

/**
 * 热更停机判定与重启编排。
 *
 * 现场（2026-10-17 frontend.log）：drain 之后后端 30s 没关掉，Runtime 强制终止它，
 * 终态 backend.spawn/stopped 携带一条 BACKEND_FORCE_TERMINATED warning。旧实现把它当
 * 「未完成优雅关闭」直接中止更新——后端已经停了、前端已经断线，用户只看到「后端更新恢复」
 * 弹窗，暂存的更新再也不会被应用。强杀只说明关得不优雅，不代表后端还在。
 */

const BASE_COMMIT = 'a'.repeat(40)
const TARGET_COMMIT = 'b'.repeat(40)
const VERSION = 'v5.7.0-beta.5'

function shutdownOutcome(options: { success: boolean; forceTerminated?: boolean }) {
  const warnings = options.forceTerminated ? [{ code: 'BACKEND_FORCE_TERMINATED' }] : []
  return {
    success: options.success,
    code: options.success ? 'BACKEND_STOPPED' : 'BACKEND_SHUTDOWN_FAILED',
    result: {
      success: options.success,
      code: options.success ? 'BACKEND_STOPPED' : 'BACKEND_SHUTDOWN_FAILED',
      message: options.success ? 'backend stopped' : 'shutdown failed',
      details: {},
    },
    warnings,
    events: [],
    errors: [],
    protocolErrors: [],
    recentLogs: [],
    logs: '',
    exitCode: 0,
    signal: null,
    stderr: '',
    argv: ['backend', 'supervise'],
    durationMs: 1,
  }
}

type Handle = {
  pid: number
  shutdown: (options?: { timeoutMs?: number; forceOnTimeout?: boolean }) => Promise<unknown>
}

function service(handle: Handle): BackendService {
  const instance = new BackendService('E:\\AUTO-MAS', {} as never)
  ;(instance as unknown as { runtimeHandle: Handle }).runtimeHandle = handle
  return instance
}

function callStop(instance: BackendService, gracefulOnly: boolean) {
  return (
    instance as unknown as {
      stopBackendViaRuntime: (
        gracefulOnly?: boolean
      ) => Promise<{ success: boolean; error?: string }>
    }
  ).stopBackendViaRuntime(gracefulOnly)
}

describe('热更停机判定', () => {
  it('Runtime 强制终止后端不算停机失败，继续应用更新', async () => {
    const handle: Handle = {
      pid: 9272,
      shutdown: vi.fn(async () => shutdownOutcome({ success: true, forceTerminated: true })),
    }

    await expect(callStop(service(handle), true)).resolves.toEqual({ success: true })
    // 热更路径不接受客户端强杀，强杀只能来自 Runtime 自己的关闭超时兜底。
    expect(handle.shutdown).toHaveBeenCalledWith(
      expect.objectContaining({ timeoutMs: 30000, forceOnTimeout: false })
    )
  })

  it('Runtime 真报关闭失败时仍然中止更新', async () => {
    const handle: Handle = {
      pid: 9272,
      shutdown: vi.fn(async () => shutdownOutcome({ success: false })),
    }

    await expect(callStop(service(handle), true)).resolves.toEqual({
      success: false,
      error: '后端未完成关闭，未应用更新',
    })
  })

  it('普通停机路径行为不变：报告失败也按已停止处理', async () => {
    const handle: Handle = {
      pid: 9272,
      shutdown: vi.fn(async () => shutdownOutcome({ success: false })),
    }

    await expect(callStop(service(handle), false)).resolves.toEqual({ success: true })
  })
})

/** 走真实的 restartStagedBackend → stopForHotUpdate → stopBackendViaRuntime，只桩掉 HTTP 与进程拉起。 */
function stagedService(options: { stopSuccess: boolean; forceTerminated?: boolean }) {
  const instance = new BackendService('E:\\AUTO-MAS', {} as never)
  const anyInst = instance as unknown as Record<string, unknown> & {
    runtimeHandle: unknown
    runtimeBaseUrl: unknown
    runtimeUpdateReady: unknown
  }
  const started: string[] = []
  anyInst.isManagedBackend = () => true
  anyInst.isHotUpdateVersionCurrent = () => true
  anyInst.runtimeUpdateReady = {
    remoteCommit: TARGET_COMMIT,
    currentCommit: BASE_COMMIT,
    version: VERSION,
  }
  anyInst.runtimeBaseUrl = 'http://127.0.0.1:36163'
  anyInst.runtimeHandle = {
    pid: 2452,
    shutdown: async () =>
      shutdownOutcome({ success: options.stopSuccess, forceTerminated: options.forceTerminated }),
  }
  anyInst.sendHotUpdateAction = async () => ({ ready: true })
  anyInst.verifyHotUpdateTarget = async () => true
  anyInst.startBackendInternal = async () => {
    started.push('start')
    anyInst.runtimeHandle = { pid: 6252 }
    return { success: true }
  }
  const restart = (
    instance as unknown as {
      restartStagedBackend: (options: unknown) => Promise<{ success: boolean; code?: string }>
    }
  ).restartStagedBackend.bind(instance)
  return { started, restart }
}

const hotUpdate = {
  operationId: '01M54PWE2Q573PCSN6JNPSZ29Y',
  baseCommit: BASE_COMMIT,
  targetCommit: TARGET_COMMIT,
  version: VERSION,
}

describe('热更重启编排', () => {
  it('强杀式停机之后仍然拉起新后端，返回成功', async () => {
    const { started, restart } = stagedService({ stopSuccess: true, forceTerminated: true })

    await expect(restart({ hotUpdate })).resolves.toEqual({ success: true })
    expect(started).toEqual(['start'])
  })

  it('停机真失败时不拉起新后端，交回停机失败结局', async () => {
    const { started, restart } = stagedService({ stopSuccess: false })

    await expect(restart({ hotUpdate })).resolves.toMatchObject({
      success: false,
      code: 'HOT_UPDATE_STOP_FAILED',
    })
    expect(started).toEqual([])
  })
})
