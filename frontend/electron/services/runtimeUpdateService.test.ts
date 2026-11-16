import { beforeEach, describe, expect, it, vi } from 'vite-plus/test'

import type { RuntimeEvent, RuntimeLaunchConfig, RuntimeRunOptions } from './runtime'
import {
  type RuntimeBinaryAlignOptions,
  type RuntimeBinaryAlignResult,
} from './runtimeBinaryService'
import { RuntimeInitializationService } from './runtimeInitializationService'
import {
  abortRuntimeUpdateForShutdown,
  cancelBackendUpdate,
  resetRuntimeUpdateSession,
  retryBackendUpdate,
  updateBackendViaRuntime,
  type BackendUpdateController,
  type RuntimeUpdateProgress,
} from './runtimeUpdateService'

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

function okResult(): RuntimeEvent {
  return {
    ...base,
    type: 'result',
    sequence: 99,
    success: true,
    code: 'OK',
    stage: 'bootstrap',
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
  status?: 'environment_broken'
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
      status: options.status ?? 'failed',
      message: options.message,
      retryable: true,
      remediation: options.remediation,
      details: {},
    } as unknown as RuntimeEvent,
  ]
}

function progressEvent(
  stage: string,
  message: string,
  status: 'running' | 'succeeded' = 'running'
): RuntimeEvent {
  return {
    ...base,
    type: 'progress',
    sequence: 20,
    stage,
    status,
    message,
  } as unknown as RuntimeEvent
}

/** 按脚本回放事件，并把每次 argv 记进公共流水。 */
class FakeRuntimeClient {
  static script: RuntimeEvent[] = []
  /** 设了闸门时，命令在回放终态事件前一直挂着，模拟长跑中的 bootstrap。 */
  static gate: Promise<void> | null = null

  async stop(): Promise<void> {
    await FakeRuntimeClient.gate
  }

  async run(command: string[], options: RuntimeRunOptions = {}) {
    callLog.push(`run:${command.join(' ')}`)
    const script = FakeRuntimeClient.script

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
      if (FakeRuntimeClient.gate && (event.type === 'error' || event.type === 'result')) {
        await FakeRuntimeClient.gate
      }
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
  onStop?: () => void | Promise<void>
}

function createBackend(options: FakeBackendOptions = {}): BackendUpdateController {
  return {
    async stopBackend() {
      callLog.push('stopBackend')
      await options.onStop?.()
      return options.stop ?? { success: true }
    },
    async startBackend() {
      callLog.push('startBackend')
      return { success: true }
    },
  }
}

function managedConfig(): RuntimeLaunchConfig {
  return { mode: 'managed', runtimePath: RUNTIME_PATH, appRoot: APP_ROOT }
}

/** 隔离联网与磁盘操作，保留更新编排的 Runtime 对齐参数检查。 */
const alignStub = {
  calls: [] as RuntimeBinaryAlignOptions[],
  /** 顺序断言要看它时打开；缺省不进流水，免得每条既有断言都要改。 */
  logCalls: false,
  async run(options: RuntimeBinaryAlignOptions): Promise<RuntimeBinaryAlignResult> {
    alignStub.calls.push(options)
    if (alignStub.logCalls) callLog.push('alignRuntime')
    return { status: 'current', target: { version: 'v0.1.10' } }
  },
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
        createClient: () => new FakeRuntimeClient() as never,
        alignRuntimeBinary: alignOptions => alignStub.run(alignOptions),
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
  alignStub.calls = []
  alignStub.logCalls = false
  FakeRuntimeClient.script = [helloEvent, okResult()]
  FakeRuntimeClient.gate = null
  resetRuntimeUpdateSession()
})

/** 取消进行中的 bootstrap 时 Runtime 给的收尾脚本。 */
function cancelledScript(): RuntimeEvent[] {
  return [
    helloEvent,
    progressEvent('workspace.clone', '正在克隆 release/v5.6.0'),
    ...failResult({
      stage: 'workspace.clone',
      code: 'OPERATION_CANCELLED',
      message: '操作已取消',
      remediation: ['retry'],
    }),
  ]
}

// ==================== 三步顺序 ====================

describe('停机 → bootstrap → 重新监督', () => {
  describe.each([
    {
      scenario: 'success',
      version: '5.6.0',
      stop: { success: true },
      expected: { success: true },
      calls: ['stopBackend', 'alignRuntime', `run:bootstrap --version ${TARGET}`, 'startBackend'],
    },
    {
      scenario: 'invalid-version',
      version: 'release/v5.6.0',
      stop: { success: true },
      expected: {
        success: false,
        phase: 'shutdown',
        code: 'INVALID_VERSION',
        retryable: false,
        remediation: ['select-version'],
      },
      calls: [],
    },
    {
      scenario: 'shutdown-failed',
      version: '5.6.0',
      stop: { success: false, error: '关闭超时' },
      expected: {
        success: false,
        phase: 'shutdown',
        error: '关闭超时',
        retryable: true,
        remediation: ['stop-backend'],
      },
      calls: ['stopBackend'],
    },
  ] as const)('更新停机 $scenario', ({ version, stop, expected, calls }) => {
    it('严格按顺序执行，bootstrap 带规范化后的目标版本', async () => {
      let releaseStop: () => void = () => undefined
      const stopGate = new Promise<void>(resolve => {
        releaseStop = resolve
      })
      let releaseRuntime: () => void = () => undefined
      FakeRuntimeClient.gate = new Promise<void>(resolve => {
        releaseRuntime = resolve
      })
      alignStub.logCalls = true
      const updating = updateBackendViaRuntime(
        version,
        collect,
        createDeps(createBackend({ stop, onStop: () => stopGate }), managedConfig())
      )

      try {
        if (calls.length > 0) {
          await vi.waitFor(() => expect(callLog).toEqual(['stopBackend']))
          expect(alignStub.calls).toHaveLength(0)
        }
        releaseStop()
        if (expected.success) {
          await vi.waitFor(() =>
            expect(callLog).toEqual([
              'stopBackend',
              'alignRuntime',
              `run:bootstrap --version ${TARGET}`,
            ])
          )
          expect(alignStub.calls[0]).toMatchObject({
            channel: 'stable',
            runtimePath: RUNTIME_PATH,
            appRoot: APP_ROOT,
          })
        }
        releaseRuntime()
        expect(await updating).toMatchObject(expected)
        expect(callLog).toEqual(calls)
        if (!expected.success) expect(alignStub.calls).toHaveLength(0)
        if (!stop.success) {
          expect(progressUpdates.at(-1)).toMatchObject({ stage: 'shutdown', status: 'failed' })
        }
      } finally {
        releaseStop()
        releaseRuntime()
        await updating
      }
    })
  })
})
// ==================== 取消 ====================

describe('取消更新', () => {
  describe.each([
    {
      shutdown: false,
      terminal: 'cancelled',
      expected: {
        success: false,
        phase: 'shutdown',
        cancelled: true,
        code: 'OPERATION_CANCELLED',
      },
      restarted: true,
    },
    {
      shutdown: false,
      terminal: 'committed',
      expected: { success: true },
      restarted: true,
    },
    {
      shutdown: false,
      terminal: 'broken',
      expected: {
        success: false,
        phase: 'bootstrap',
        code: 'DEPENDENCY_SYNC_FAILED',
        cancelled: true,
        retryActions: ['dependencies-sync', 'dependencies-rebuild', 'repair'],
      },
      restarted: false,
    },
    {
      shutdown: true,
      terminal: 'cancelled',
      expected: {
        success: false,
        phase: 'shutdown',
        cancelled: true,
        code: 'OPERATION_CANCELLED',
      },
      restarted: false,
    },
    {
      shutdown: true,
      terminal: 'committed',
      expected: { success: false, phase: 'restart', cancelled: true },
      restarted: false,
    },
    {
      shutdown: true,
      terminal: 'broken',
      expected: {
        success: false,
        phase: 'bootstrap',
        code: 'DEPENDENCY_SYNC_FAILED',
        cancelled: true,
        retryActions: ['dependencies-sync', 'dependencies-rebuild', 'repair'],
      },
      restarted: false,
    },
  ] as const)('取消更新 terminal=$terminal shutdown=$shutdown', scenario => {
    it('bootstrap 进行中取消：OPERATION_CANCELLED 意味着源码没动，把旧后端拉回来', async () => {
      const { shutdown, terminal, expected, restarted } = scenario
      const committed = progressEvent('workspace.swap', '源码已替换', 'succeeded')
      FakeRuntimeClient.script =
        terminal === 'cancelled'
          ? cancelledScript()
          : terminal === 'committed'
            ? [helloEvent, committed, okResult()]
            : [
                helloEvent,
                committed,
                ...failResult({
                  stage: 'dependencies.sync',
                  code: 'DEPENDENCY_SYNC_FAILED',
                  message: 'uv sync 失败',
                  remediation: ['retry-sync', 'rebuild-environment'],
                  status: 'environment_broken',
                }),
              ]
      let releaseGate: () => void = () => undefined
      FakeRuntimeClient.gate = new Promise<void>(resolve => {
        releaseGate = resolve
      })
      const updating = updateBackendViaRuntime(
        '5.6.0',
        collect,
        createDeps(createBackend(), managedConfig())
      )
      let abortSettled = false
      let aborting: ReturnType<typeof abortRuntimeUpdateForShutdown> | undefined
      try {
        await vi.waitFor(() => expect(callLog).toContain(`run:bootstrap --version ${TARGET}`))
        if (shutdown) {
          aborting = abortRuntimeUpdateForShutdown(1000).then(result => {
            abortSettled = true
            return result
          })
        } else {
          expect(cancelBackendUpdate()).toEqual({ accepted: true, forwarded: true })
        }
        await vi.waitFor(() => expect(callLog).toContain('stdin:cancel'))
        expect(callLog).toEqual([
          'stopBackend',
          `run:bootstrap --version ${TARGET}`,
          'stdin:cancel',
        ])
        if (shutdown) expect(abortSettled).toBe(false)
        releaseGate()

        const outcome = await updating
        expect(outcome).toMatchObject(expected)
        if (terminal === 'cancelled') expect(outcome.retryActions).toBeUndefined()
        if (outcome.success) expect(outcome.cancelled).toBeUndefined()
        if (aborting) {
          expect(await aborting).toEqual({ hadSession: true, forwarded: true, settled: true })
          expect(cancelBackendUpdate()).toEqual({ accepted: false, forwarded: false })
          expect(await retryBackendUpdate('dependencies-sync', collect)).toMatchObject({
            success: false,
            retryable: false,
          })
        }
        expect(callLog).toEqual([
          'stopBackend',
          `run:bootstrap --version ${TARGET}`,
          'stdin:cancel',
          ...(restarted ? ['startBackend'] : []),
        ])
        if (restarted) {
          expect(progressUpdates.at(-1)).toMatchObject({ stage: 'restart', status: 'completed' })
        }
      } finally {
        releaseGate()
        await Promise.all([updating, aborting])
      }
    })
  })
})
