import { readFileSync } from 'node:fs'
import { mkdtemp, rm } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { beforeEach, describe, expect, it, vi } from 'vite-plus/test'

import type { RuntimeEvent, RuntimeLaunchConfig, RuntimeRunOptions } from './runtime'
import {
  RUNTIME_BINARY_CANCELLED,
  RUNTIME_LATEST_UNAVAILABLE,
  type RuntimeBinaryAlignOptions,
  type RuntimeBinaryAlignResult,
} from './runtimeBinaryService'
import { RuntimeInitializationService } from './runtimeInitializationService'
import { canRetryStartup } from './startupRecovery'
import { StartupHardwareLog } from './startupHardware/localLog'
import {
  claimStartupAttempt,
  clearStartupHardware,
  finishStartupAttempt,
  localStartupAttempt,
  operationAttempt,
  setupStartupHardware,
} from './startupHardware/monitor'

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

const fixturesDir = join(dirname(fileURLToPath(import.meta.url)), 'runtime', '__fixtures__')

/** 夹具由本机构建的 auto-mas-runtime.exe 真实跑出来，不是手写的。 */
function fixtureEvents(name: string): RuntimeEvent[] {
  return readFileSync(join(fixturesDir, name), 'utf8')
    .split('\n')
    .filter(line => line.trim() !== '')
    .map(line => JSON.parse(line) as RuntimeEvent)
}

// ==================== 假 RuntimeClient ====================

const APP_ROOT = 'D:\\AUTO-MAS'
const RUNTIME_PATH = 'D:\\AUTO-MAS\\runtime\\auto-mas-runtime.exe'

interface FakeCall {
  command: string[]
  runtimePath: string
}

/** 记录执行路径与命令，并按脚本回放事件。 */
class FakeRuntimeClient {
  static calls: FakeCall[] = []
  /** 依次消费：每次 run 取一条脚本，用完则复用最后一条。 */
  static scripts: { events: RuntimeEvent[] }[] = []

  constructor(readonly options: { runtimePath: string; appRoot: string }) {}

  async run(command: string[], options: RuntimeRunOptions = {}) {
    FakeRuntimeClient.calls.push({
      command,
      runtimePath: this.options.runtimePath,
    })

    const script =
      FakeRuntimeClient.scripts[
        Math.min(FakeRuntimeClient.calls.length - 1, FakeRuntimeClient.scripts.length - 1)
      ]
    if (!script) throw new Error('测试未准备事件脚本')

    let result: RuntimeEvent | undefined
    const errors: RuntimeEvent[] = []
    for (const event of script.events) {
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
      hello: script.events[0],
      result,
      success: result.success,
      code: result.code,
      events: script.events,
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

// ==================== 假的第 0 步 ====================

/**
 * 第 0 步（Runtime 对齐）的桩：记录每次调用的参数，按脚本给结果；`hold` 让它停住，
 * 用来验证取消与「bootstrap 要等它」。
 */
const alignStub = {
  calls: [] as RuntimeBinaryAlignOptions[],
  result: { status: 'current', target: { version: 'v0.1.7' } } as RuntimeBinaryAlignResult,
  hold: null as Promise<void> | null,
  throws: null as unknown,
  async run(options: RuntimeBinaryAlignOptions): Promise<RuntimeBinaryAlignResult> {
    alignStub.calls.push(options)
    if (alignStub.throws) throw alignStub.throws
    if (alignStub.hold) await alignStub.hold
    return alignStub.result
  },
}

function createService(overrides: Partial<RuntimeLaunchConfig> = {}) {
  const launchConfig: RuntimeLaunchConfig = {
    mode: 'managed',
    runtimePath: RUNTIME_PATH,
    appRoot: APP_ROOT,
    dataRoot: APP_ROOT,
    ...overrides,
  }
  return new RuntimeInitializationService({
    launchConfig,
    createClient: options => new FakeRuntimeClient(options) as never,
    alignRuntimeBinary: options => alignStub.run(options),
  })
}

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
  capabilities: [],
} as unknown as RuntimeEvent

function okResult(stage: string): RuntimeEvent {
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

type ResultEvent = Extract<RuntimeEvent, { type: 'result' }>
function failedResult(stage: ResultEvent['stage'], code: ResultEvent['code']): ResultEvent {
  return {
    ...base,
    protocol: 1,
    type: 'result',
    sequence: 99,
    success: false,
    code,
    stage,
    status: 'failed',
    message: '准备失败',
    retryable: true,
    remediation: ['retry'],
    details: {},
  }
}

beforeEach(() => {
  FakeRuntimeClient.calls = []
  FakeRuntimeClient.scripts = [{ events: [helloEvent, okResult('bootstrap')] }]
  alignStub.calls = []
  alignStub.result = { status: 'current', target: { version: 'v0.1.7' } }
  alignStub.hold = null
  alignStub.throws = null
})

it('失败页更新 Runtime 时采样，更新失败可导出现场，成功后由初始化接回同一次下载', async () => {
  const directory = await mkdtemp(join(tmpdir(), 'mas-hardware-recovery-'))
  const log = new StartupHardwareLog(directory)
  const reportHostFailure = vi.fn()
  setupStartupHardware(
    () => ({
      log,
      directories: [],
      scope: 'managed',
      acceleration: 'unknown',
      graphics: async () => ({}),
      reportHostFailure,
    }),
    () => 1
  )
  try {
    finishStartupAttempt(claimStartupAttempt(), 'failure', 'backend')
    const service = createService()
    const transfer = () => operationAttempt()?.beginDesktopDownload(1)?.(32 * 2 ** 20, undefined)
    const failed = await service.updateRuntimeBinary(
      () => {},
      undefined,
      async () => {
        transfer()
        throw new Error('download interrupted')
      }
    )
    expect(failed.status).toBe('failed')
    expect(reportHostFailure).toHaveBeenCalledWith('runtime_binary', 'unknown')
    expect(localStartupAttempt()).toBeUndefined()
    await log.drain()
    const rows = readFileSync(join(directory, 'startup-hardware.log'), 'utf8')
      .trim()
      .split('\n')
      .map(line => JSON.parse(line))
    expect(rows).toContainEqual(
      expect.objectContaining({ event: '失败前15秒', stage: 'runtime_binary' })
    )
    const upgraded = await service.updateRuntimeBinary(
      () => {},
      undefined,
      async () => {
        transfer()
        return { status: 'upgraded' }
      }
    )
    expect(upgraded.status).toBe('upgraded')
    expect(finishStartupAttempt(claimStartupAttempt(), 'success', 'none')).toMatchObject({
      downloaded: '16-128MiB',
    })
  } finally {
    clearStartupHardware()
    await log.drain()
    await rm(directory, { recursive: true, force: true })
  }
})

// ==================== 第 0 步：Runtime 对齐 ====================

describe('第 0 步：bootstrap 之前先对齐 Runtime', () => {
  describe.each(['installed', 'missing', 'exception', 'unavailable', 'offline'] as const)(
    'Runtime 对齐 scenario=%s',
    scenario => {
      it('按目标版本的发布通道、当前 exe 与 app-root 调用对齐，且在 bootstrap 命令之前', async () => {
        const processWithResources = process as NodeJS.Process & { resourcesPath?: string }
        const previousResources = processWithResources.resourcesPath
        processWithResources.resourcesPath = join(APP_ROOT, 'resources')
        const runtimePath =
          scenario === 'missing'
            ? join(processWithResources.resourcesPath, 'auto-mas-runtime.exe')
            : RUNTIME_PATH
        alignStub.result =
          scenario === 'unavailable' || scenario === 'offline'
            ? {
                status: 'failed',
                code: RUNTIME_LATEST_UNAVAILABLE,
                error: '无法确认线上最新的 Runtime 版本：CNB 与 GitHub 都没有给出结果',
                ...(scenario === 'offline' ? { networkUnavailable: true as const } : {}),
              }
            : { status: 'upgraded', target: { version: 'v0.1.10' } }
        alignStub.throws =
          scenario === 'exception' ? new Error('unexpected alignment failure') : null
        FakeRuntimeClient.scripts = [{ events: fixtureEvents('bootstrap-success.ndjson') }]
        let release: () => void = () => undefined
        alignStub.hold = new Promise<void>(resolve => {
          release = resolve
        })
        const service = createService({ runtimePath: scenario === 'missing' ? null : RUNTIME_PATH })
        const pending = service.bootstrap(() => undefined)

        try {
          await vi.waitFor(() => expect(alignStub.calls).toHaveLength(1))
          expect(FakeRuntimeClient.calls).toHaveLength(0)
          release()
          const outcome = await pending

          expect(alignStub.calls).toHaveLength(1)
          expect(alignStub.calls[0]).toMatchObject({
            channel: 'prerelease',
            runtimePath,
            appRoot: APP_ROOT,
          })
          if (scenario === 'exception' || scenario === 'unavailable') {
            expect(outcome).toMatchObject({
              success: false,
              code:
                scenario === 'exception'
                  ? 'RUNTIME_BINARY_ALIGN_ERROR'
                  : RUNTIME_LATEST_UNAVAILABLE,
              retryable: true,
              remediation: ['retry', 'open-log'],
              failedStage: 'python',
              failureOrigin: 'runtime_binary',
            })
            expect(canRetryStartup(outcome)).toBe(false)
            expect(FakeRuntimeClient.calls).toHaveLength(0)
            return
          }

          expect(outcome.success).toBe(true)
          expect(FakeRuntimeClient.calls).toMatchObject([
            {
              runtimePath,
              command: [
                'bootstrap',
                '--version',
                'v5.5.0-beta.3',
                ...(scenario === 'offline' ? ['--if-needed'] : []),
              ],
            },
          ])
        } finally {
          release()
          await pending
          if (previousResources === undefined) delete processWithResources.resourcesPath
          else processWithResources.resourcesPath = previousResources
        }
      })
    }
  )

  describe.each([
    { status: 'cancelled', code: RUNTIME_BINARY_CANCELLED },
    { status: 'upgraded', target: { version: 'v0.1.10' } },
  ] as const)('取消对齐 result=$status', alignment => {
    it('第 0 步期间 cancel() 生效：对齐看到取消判据，结果是 OPERATION_CANCELLED 且不跑 bootstrap', async () => {
      let release: () => void = () => undefined
      alignStub.hold = new Promise<void>(resolve => {
        release = resolve
      })
      const service = createService()
      alignStub.result = alignment
      const pending = service.bootstrap(() => undefined)
      try {
        await vi.waitFor(() => expect(alignStub.calls).toHaveLength(1))
        expect(service.cancel()).toBe(true)
        expect(alignStub.calls[0].isCancelled?.()).toBe(true)
        release()
        const outcome = await pending

        expect(outcome).toMatchObject({
          success: false,
          code: RUNTIME_BINARY_CANCELLED,
          failureOrigin: 'runtime_binary',
        })
        expect(FakeRuntimeClient.calls).toHaveLength(0)
      } finally {
        release()
        await pending
      }
    })
  })
})

// ==================== 单步重试 ====================

describe('分段恢复的完整性', () => {
  it('依赖重试发现 Python 缺失时先修复 Python，再恢复依赖', async () => {
    FakeRuntimeClient.scripts = [
      { events: [helloEvent, failedResult('dependencies.check', 'PYTHON_VERSION_MISMATCH')] },
      { events: [helloEvent, okResult('python.install')] },
      { events: [helloEvent, okResult('dependencies.sync')] },
    ]
    expect(await createService().retryStage('dependency', () => undefined)).toMatchObject({
      success: true,
    })
    expect(FakeRuntimeClient.calls.map(call => call.command)).toEqual([
      ['dependencies', 'sync'],
      ['environment', 'repair'],
      ['dependencies', 'sync'],
    ])
  })

  it('锁文件损坏时通过完整准备恢复受管源码', async () => {
    alignStub.result = {
      status: 'current',
      target: { version: 'v0.1.28' },
      bootstrapEnvironmentReuse: true,
    }
    FakeRuntimeClient.scripts = [
      { events: [helloEvent, failedResult('dependencies.check', 'LOCKFILE_INVALID')] },
      { events: [helloEvent, okResult('bootstrap')] },
    ]
    expect(await createService().retryStage('dependency', () => undefined)).toMatchObject({
      success: true,
    })
    expect(FakeRuntimeClient.calls.map(call => call.command)).toEqual([
      ['dependencies', 'sync'],
      ['bootstrap', '--version', 'v5.5.0-beta.3'],
    ])
  })
})
