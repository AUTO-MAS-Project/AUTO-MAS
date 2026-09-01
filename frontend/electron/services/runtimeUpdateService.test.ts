import { beforeEach, describe, expect, it, vi } from 'vitest'

import {
  cancelBackendUpdate,
  describeRetryAction,
  normalizeRuntimeUpdateVersion,
  resetRuntimeUpdateSession,
  resolveRetryActions,
  retryBackendUpdate,
  updateBackendViaRuntime,
  type BackendUpdateController,
  type RuntimeUpdateProgress,
} from './runtimeUpdateService'
import { RuntimeInitializationService } from './runtimeInitializationService'
import type { RuntimeEvent, RuntimeLaunchConfig, RuntimeRunOptions } from './runtime'

vi.mock('electron', () => ({ app: { getVersion: () => '5.5.0-beta.3' } }))
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

const APP_ROOT = 'D:\\AUTO-MAS'
const RUNTIME_PATH = 'D:\\AUTO-MAS\\runtime\\auto-mas-runtime.exe'
const TARGET = 'v5.6.0'

/** 停机、Runtime 命令与重启共用一条调用流水，顺序断言只看它。 */
let callLog: string[] = []

// ==================== 假件 ====================

const base = {
  protocol: 1,
  operationId: '01M1F6M33JFZZ7Y85BE5S849ZN',
  timestamp: '2026-09-01T22:03:00.000+02:00',
}

const helloEvent = {
  ...base,
  type: 'hello',
  sequence: 1,
  runtimeVersion: 'dev',
  command: 'bootstrap',
  capabilities: ['stdin.cancel'],
} as unknown as RuntimeEvent

function okResult(stage = 'bootstrap'): RuntimeEvent {
  return {
    ...base,
    type: 'result',
    sequence: 99,
    success: true,
    code: 'OK',
    stage,
    status: 'succeeded',
    message: '完成',
    retryable: false,
    remediation: [],
    details: {},
  } as unknown as RuntimeEvent
}

function failResult(options: {
  stage: string
  code: string
  message: string
  remediation: string[]
  logPath?: string
}): RuntimeEvent[] {
  return [
    {
      ...base,
      type: 'error',
      sequence: 40,
      code: options.code,
      stage: options.stage,
      message: options.message,
      retryable: true,
      remediation: options.remediation,
      details: {},
    } as unknown as RuntimeEvent,
    {
      ...base,
      type: 'result',
      sequence: 99,
      success: false,
      // 顶层 result 带的是 `bootstrap`，失败段必须从 error 事件上取。
      stage: 'bootstrap',
      code: options.code,
      status: 'failed',
      message: options.message,
      retryable: true,
      remediation: options.remediation,
      details: options.logPath ? { logPath: options.logPath } : {},
    } as unknown as RuntimeEvent,
  ]
}

function progressEvent(stage: string, message: string): RuntimeEvent {
  return {
    ...base,
    type: 'progress',
    sequence: 20,
    stage,
    status: 'running',
    message,
  } as unknown as RuntimeEvent
}

function logEvent(stream: 'stdout' | 'stderr', message: string): RuntimeEvent {
  return {
    ...base,
    type: 'log',
    sequence: 10,
    stage: 'dependencies.sync',
    stream,
    message,
  } as unknown as RuntimeEvent
}

/** 按脚本回放事件，并把每次 argv 记进公共流水。 */
class FakeRuntimeClient {
  static scripts: RuntimeEvent[][] = []
  static index = 0

  constructor(readonly options: { runtimePath: string; appRoot: string }) {}

  async run(command: string[], options: RuntimeRunOptions = {}) {
    callLog.push(`run:${command.join(' ')}`)
    const script =
      FakeRuntimeClient.scripts[
        Math.min(FakeRuntimeClient.index++, FakeRuntimeClient.scripts.length - 1)
      ]
    if (!script) throw new Error('测试未准备事件脚本')

    options.onStarted?.({
      pid: 4242,
      sendControl: () => 'CMD',
      cancel: () => {
        callLog.push('stdin:cancel')
        return 'CMD'
      },
      kill: () => undefined,
    })

    let result: RuntimeEvent | undefined
    const errors: RuntimeEvent[] = []
    for (const event of script) {
      switch (event.type) {
        case 'progress':
          options.onProgress?.(event)
          break
        case 'state':
          options.onState?.(event)
          break
        case 'log':
          options.onLog?.(event)
          break
        case 'error':
          errors.push(event)
          options.onRuntimeError?.(event)
          break
        case 'result':
          result = event
          break
      }
    }

    if (!result || result.type !== 'result') throw new Error('测试脚本缺少 result 事件')
    return {
      hello: script[0],
      result,
      success: result.success,
      code: result.code,
      events: script,
      warnings: [],
      errors,
      logs: {},
      protocolErrors: [],
      exitCode: result.success ? 0 : 50,
      signal: null,
      stderr: '',
      argv: command,
      durationMs: 1,
    }
  }
}

interface FakeBackendOptions {
  stop?: { success: boolean; error?: string }
  start?: { success: boolean; error?: string; logs?: string; code?: string }
  onStop?: () => void
}

function createBackend(options: FakeBackendOptions = {}): BackendUpdateController {
  return {
    async stopBackend() {
      callLog.push('stopBackend')
      options.onStop?.()
      return options.stop ?? { success: true }
    },
    async startBackend() {
      callLog.push('startBackend')
      return options.start ?? { success: true }
    },
  }
}

function managedConfig(): RuntimeLaunchConfig {
  return { mode: 'managed', runtimePath: RUNTIME_PATH, appRoot: APP_ROOT }
}

function developmentConfig(): RuntimeLaunchConfig {
  return { mode: 'development', runtimePath: RUNTIME_PATH, appRoot: APP_ROOT, repo: APP_ROOT }
}

function createDeps(backend: BackendUpdateController, launchConfig: RuntimeLaunchConfig) {
  return {
    backend,
    launchConfig,
    createRuntimeService: (
      options: ConstructorParameters<typeof RuntimeInitializationService>[0]
    ) =>
      new RuntimeInitializationService({
        ...options,
        createClient: clientOptions => new FakeRuntimeClient(clientOptions) as never,
      }),
  }
}

const progressUpdates: RuntimeUpdateProgress[] = []
const collect = (update: RuntimeUpdateProgress): void => {
  progressUpdates.push(update)
}

beforeEach(() => {
  callLog = []
  progressUpdates.length = 0
  FakeRuntimeClient.scripts = [[helloEvent, okResult()]]
  FakeRuntimeClient.index = 0
  resetRuntimeUpdateSession()
})

// ==================== 版本号 ====================

describe('目标版本规范化', () => {
  it('补齐 v 前缀并去掉首尾空白', () => {
    expect(normalizeRuntimeUpdateVersion('5.6.0')).toBe('v5.6.0')
    expect(normalizeRuntimeUpdateVersion('v5.6.0')).toBe('v5.6.0')
    expect(normalizeRuntimeUpdateVersion('  v5.5.0-beta.3  ')).toBe('v5.5.0-beta.3')
    expect(normalizeRuntimeUpdateVersion('5.5.0-beta.3')).toBe('v5.5.0-beta.3')
  })

  it('路径分隔符、空白与 .. 一律判非法', () => {
    expect(normalizeRuntimeUpdateVersion('release/v5.6.0')).toBeNull()
    expect(normalizeRuntimeUpdateVersion('v5.6.0/../main')).toBeNull()
    expect(normalizeRuntimeUpdateVersion('v5.6.0\\evil')).toBeNull()
    expect(normalizeRuntimeUpdateVersion('v5.6 .0')).toBeNull()
    expect(normalizeRuntimeUpdateVersion('..')).toBeNull()
    expect(normalizeRuntimeUpdateVersion('')).toBeNull()
    expect(normalizeRuntimeUpdateVersion('   ')).toBeNull()
    expect(normalizeRuntimeUpdateVersion('latest')).toBeNull()
    expect(normalizeRuntimeUpdateVersion(undefined)).toBeNull()
    expect(normalizeRuntimeUpdateVersion(5.6)).toBeNull()
  })

  it('非法版本直接拒绝，不动后端也不调 Runtime', async () => {
    const outcome = await updateBackendViaRuntime(
      'release/v5.6.0',
      collect,
      createDeps(createBackend(), managedConfig())
    )

    expect(outcome.success).toBe(false)
    expect(outcome.phase).toBe('shutdown')
    expect(outcome.code).toBe('INVALID_VERSION')
    expect(callLog).toEqual([])
  })
})

// ==================== 三步顺序 ====================

describe('停机 → bootstrap → 重新监督', () => {
  it('严格按顺序执行，bootstrap 带规范化后的目标版本', async () => {
    const outcome = await updateBackendViaRuntime(
      '5.6.0',
      collect,
      createDeps(createBackend(), managedConfig())
    )

    expect(outcome.success).toBe(true)
    expect(callLog).toEqual(['stopBackend', `run:bootstrap --version ${TARGET}`, 'startBackend'])
  })

  it('首尾各补一个停机与重启的进度态，中间沿用初始化界面的段', async () => {
    await updateBackendViaRuntime('5.6.0', collect, createDeps(createBackend(), managedConfig()))

    expect(progressUpdates[0]).toEqual({
      stage: 'shutdown',
      status: 'started',
      progress: 0,
      message: '正在停止当前后端',
    })
    expect(progressUpdates.at(-1)).toMatchObject({ stage: 'restart', status: 'completed' })
    // W9b 的接管逻辑照搬：mirror / pip / git 在进 bootstrap 时立刻置完成。
    const takenOver = progressUpdates.filter(update => update.message === '由 Runtime 接管')
    expect(takenOver.map(update => update.stage)).toEqual(['mirror', 'pip', 'git'])
  })

  it('停不掉旧后端时结局是 shutdown，bootstrap 根本不跑', async () => {
    const backend = createBackend({ stop: { success: false, error: '关闭超时' } })
    const outcome = await updateBackendViaRuntime(
      '5.6.0',
      collect,
      createDeps(backend, managedConfig())
    )

    expect(outcome).toMatchObject({
      success: false,
      phase: 'shutdown',
      error: '关闭超时',
      retryable: true,
      remediation: ['stop-backend'],
    })
    expect(callLog).toEqual(['stopBackend'])
    expect(progressUpdates.at(-1)).toMatchObject({ stage: 'shutdown', status: 'failed' })
  })
})

// ==================== bootstrap 失败 ====================

describe('bootstrap 失败的两种现场', () => {
  it('克隆失败：旧 repo 保留，重试入口是 workspace sync --version', async () => {
    FakeRuntimeClient.scripts = [
      [
        helloEvent,
        ...failResult({
          stage: 'workspace.clone',
          code: 'GIT_CLONE_FAILED',
          message: '浅克隆 release/v5.6.0 失败',
          remediation: ['retry', 'retry-other-mirror'],
          logPath: 'D:\\AUTO-MAS\\logs\\runtime\\bootstrap-20260901.log',
        }),
      ],
    ]

    const outcome = await updateBackendViaRuntime(
      '5.6.0',
      collect,
      createDeps(createBackend(), managedConfig())
    )

    expect(outcome).toMatchObject({
      success: false,
      phase: 'bootstrap',
      code: 'GIT_CLONE_FAILED',
      retryable: true,
      remediation: ['retry', 'retry-other-mirror'],
      logPath: 'D:\\AUTO-MAS\\logs\\runtime\\bootstrap-20260901.log',
      retryActions: ['workspace-sync'],
    })
    // 后端没能起回来，也不该被偷偷拉起。
    expect(callLog).toEqual(['stopBackend', `run:bootstrap --version ${TARGET}`])
    expect(describeRetryAction('workspace-sync')).toEqual([
      'workspace',
      'sync',
      '--version',
      TARGET,
    ])
  })

  it('依赖同步失败：environment_broken，三个重试入口各自对应正确的命令', async () => {
    FakeRuntimeClient.scripts = [
      [
        helloEvent,
        logEvent('stdout', 'Resolved 210 packages'),
        logEvent('stderr', 'error: failed to build wheel'),
        ...failResult({
          stage: 'dependencies.sync',
          code: 'DEPENDENCY_SYNC_FAILED',
          message: 'uv sync 失败',
          remediation: ['retry-sync', 'rebuild-environment'],
        }),
      ],
    ]

    const outcome = await updateBackendViaRuntime(
      '5.6.0',
      collect,
      createDeps(createBackend(), managedConfig())
    )

    expect(outcome).toMatchObject({
      success: false,
      phase: 'bootstrap',
      code: 'DEPENDENCY_SYNC_FAILED',
      remediation: ['retry-sync', 'rebuild-environment'],
      retryActions: ['dependencies-sync', 'dependencies-rebuild', 'repair'],
    })
    expect(outcome.logs).toContain('[stdout]')
    expect(outcome.logs).toContain('[stderr]')

    expect(describeRetryAction('dependencies-sync')).toEqual(['dependencies', 'sync'])
    expect(describeRetryAction('dependencies-rebuild')).toEqual(['dependencies', 'rebuild'])
    expect(describeRetryAction('repair')).toEqual(['repair'])
  })

  it('单步重试成功后继续把后端拉起来', async () => {
    FakeRuntimeClient.scripts = [
      [
        helloEvent,
        ...failResult({
          stage: 'dependencies.sync',
          code: 'DEPENDENCY_SYNC_FAILED',
          message: 'uv sync 失败',
          remediation: ['retry-sync', 'rebuild-environment'],
        }),
      ],
      [helloEvent, okResult('dependencies.sync')],
    ]

    await updateBackendViaRuntime('5.6.0', collect, createDeps(createBackend(), managedConfig()))
    callLog = []

    const retried = await retryBackendUpdate('dependencies-sync', collect)

    expect(retried.success).toBe(true)
    // 上一次失败给了 rebuild-environment，但显式选「重试同步」时不能被改写成 rebuild。
    expect(callLog).toEqual(['run:dependencies sync', 'startBackend'])
  })

  it('失败段到重试入口的映射', () => {
    expect(resolveRetryActions('repository')).toEqual(['workspace-sync'])
    expect(resolveRetryActions('dependency')).toEqual([
      'dependencies-sync',
      'dependencies-rebuild',
      'repair',
    ])
    expect(resolveRetryActions('python')).toEqual(['repair'])
    expect(resolveRetryActions(undefined)).toEqual(['repair'])
  })
})

// ==================== 新后端起不来 ====================

describe('重新监督失败', () => {
  it('结局是 restart，展示 formatStartupLogs 的整块日志', async () => {
    const backend = createBackend({
      start: {
        success: false,
        error: '后端在就绪前结束（BACKEND_EXITED_BEFORE_READY）',
        code: 'BACKEND_EXITED_BEFORE_READY',
        logs: '[stdout]\nINFO 启动中\n\n[stderr]\nModuleNotFoundError: no module named app',
      },
    })

    const outcome = await updateBackendViaRuntime(
      '5.6.0',
      collect,
      createDeps(backend, managedConfig())
    )

    expect(outcome).toMatchObject({
      success: false,
      phase: 'restart',
      code: 'BACKEND_EXITED_BEFORE_READY',
    })
    expect(outcome.logs).toContain('[stdout]')
    expect(outcome.logs).toContain('[stderr]')
    expect(callLog).toEqual(['stopBackend', `run:bootstrap --version ${TARGET}`, 'startBackend'])
    expect(progressUpdates.at(-1)).toMatchObject({ stage: 'restart', status: 'failed' })
  })
})

// ==================== 取消 ====================

describe('取消更新', () => {
  it('bootstrap 开始前取消：不跑 Runtime 命令，把旧后端拉回来', async () => {
    const backend = createBackend({
      onStop: () => {
        cancelBackendUpdate()
      },
    })

    const outcome = await updateBackendViaRuntime(
      '5.6.0',
      collect,
      createDeps(backend, managedConfig())
    )

    expect(outcome).toMatchObject({ success: false, phase: 'shutdown', cancelled: true })
    expect(callLog).toEqual(['stopBackend', 'startBackend'])
  })

  it('bootstrap 进行中取消：走 stdin cancel，结局仍按 Runtime 给的 result 算', async () => {
    FakeRuntimeClient.scripts = [
      [
        helloEvent,
        progressEvent('workspace.clone', '正在克隆 release/v5.6.0'),
        ...failResult({
          stage: 'workspace.clone',
          code: 'OPERATION_CANCELLED',
          message: '操作已取消',
          remediation: ['retry'],
        }),
      ],
    ]

    const outcome = await updateBackendViaRuntime(
      '5.6.0',
      update => {
        collect(update)
        // 克隆刚开始时按下取消，等价于用户在进度弹窗上点「取消更新」。
        if (update.stage === 'repository' && update.status === 'started') cancelBackendUpdate()
      },
      createDeps(createBackend(), managedConfig())
    )

    expect(callLog).toEqual(['stopBackend', `run:bootstrap --version ${TARGET}`, 'stdin:cancel'])
    expect(outcome).toMatchObject({
      success: false,
      phase: 'bootstrap',
      cancelled: true,
      code: 'OPERATION_CANCELLED',
      retryActions: ['workspace-sync'],
    })
  })

  it('没有进行中的会话时取消不受理', () => {
    expect(cancelBackendUpdate()).toEqual({ accepted: false, forwarded: false })
  })
})

// ==================== 模式分流 ====================

describe('模式分流', () => {
  it('development 模式直接返回不支持，一条 Runtime 命令都不发', async () => {
    const outcome = await updateBackendViaRuntime(
      '5.6.0',
      collect,
      createDeps(createBackend(), developmentConfig())
    )

    expect(outcome).toMatchObject({
      success: false,
      unsupported: true,
      code: 'RUNTIME_UPDATE_UNSUPPORTED',
      retryable: false,
    })
    expect(callLog).toEqual([])
    expect(progressUpdates).toEqual([])
  })

  it('灰度开关关闭时同样不接管', async () => {
    const outcome = await updateBackendViaRuntime(
      '5.6.0',
      collect,
      createDeps(createBackend(), { mode: 'off', runtimePath: null, appRoot: APP_ROOT })
    )

    expect(outcome.unsupported).toBe(true)
    expect(callLog).toEqual([])
  })
})
