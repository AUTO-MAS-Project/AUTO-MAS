import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { beforeEach, describe, expect, it, vi } from 'vite-plus/test'

import type { MirrorConfig, MirrorSource } from './mirrorService'
import type { RuntimeEvent, RuntimeRunOptions, RuntimeSupervisedLaunchConfig } from './runtime'
import {
  RUNTIME_BINARY_CANCELLED,
  RUNTIME_LATEST_UNAVAILABLE,
  type RuntimeBinaryAlignOptions,
  type RuntimeBinaryAlignResult,
} from './runtimeBinaryService'
import {
  BootstrapProgressUpdate,
  MirrorLookup,
  RUNTIME_TAKEOVER_MESSAGE,
  RuntimeInitializationService,
} from './runtimeInitializationService'

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
  mirrors: { kind: string; key: string }[]
}

/** 记录每次调用的 argv 与镜像选项，并按脚本回放事件。 */
class FakeRuntimeClient {
  static calls: FakeCall[] = []
  /** 依次消费：每次 run 取一条脚本，用完则复用最后一条。 */
  static scripts: { events: RuntimeEvent[]; throws?: unknown }[] = []

  constructor(readonly options: { runtimePath: string; appRoot: string; mirrors?: unknown[] }) {}

  async run(command: string[], options: RuntimeRunOptions = {}) {
    FakeRuntimeClient.calls.push({
      command,
      mirrors: (this.options.mirrors ?? []) as { kind: string; key: string }[],
    })

    const script =
      FakeRuntimeClient.scripts[
        Math.min(FakeRuntimeClient.calls.length - 1, FakeRuntimeClient.scripts.length - 1)
      ]
    if (!script) throw new Error('测试未准备事件脚本')
    if (script.throws) throw script.throws

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

// ==================== 假 MirrorService ====================

/** key/name 组合与 mirrorService.ts 的默认配置一致，覆盖测试要用到的三类、含中文 name。 */
const FAKE_MIRROR_SOURCES: Readonly<Record<string, MirrorSource[]>> = {
  python: [
    { key: 'aliyun', name: '阿里云镜像', url: '', type: 'mirror', description: '' },
    { key: 'official', name: 'Python 官方', url: '', type: 'official', description: '' },
  ],
  repo: [
    { key: 'cnb', name: 'CNB 官方镜像', url: '', type: 'mirror', description: '' },
    { key: 'github', name: 'GitHub 官方', url: '', type: 'official', description: '' },
    {
      key: 'ghproxy_edgeone',
      name: 'gh-proxy (EdgeOne)',
      url: '',
      type: 'mirror',
      description: '',
    },
    { key: 'ghfast', name: 'ghfast 镜像', url: '', type: 'mirror', description: '' },
  ],
  pip_mirror: [
    { key: 'aliyun', name: '阿里云', url: '', type: 'mirror', description: '' },
    { key: 'tsinghua', name: '清华大学', url: '', type: 'mirror', description: '' },
    { key: 'ustc', name: '中科大', url: '', type: 'mirror', description: '' },
    { key: 'official', name: 'PyPI 官方', url: '', type: 'official', description: '' },
  ],
}

/** 只实现 mapMirrorSelection 需要的 getMirrors，不碰真实 MirrorService 的文件读写。 */
function fakeMirrorService(): MirrorLookup {
  return {
    getMirrors: (type: keyof MirrorConfig) => FAKE_MIRROR_SOURCES[type] ?? [],
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

function createService(
  overrides: Partial<RuntimeSupervisedLaunchConfig> = {},
  mirrorService: MirrorLookup = fakeMirrorService()
) {
  const launchConfig: RuntimeSupervisedLaunchConfig = {
    mode: 'managed',
    runtimePath: RUNTIME_PATH,
    appRoot: APP_ROOT,
    dataRoot: APP_ROOT,
    ...overrides,
  }
  return new RuntimeInitializationService({
    launchConfig,
    mirrorService,
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

beforeEach(() => {
  FakeRuntimeClient.calls = []
  FakeRuntimeClient.scripts = [{ events: [helloEvent, okResult('bootstrap')] }]
  alignStub.calls = []
  alignStub.result = { status: 'current', target: { version: 'v0.1.7' } }
  alignStub.hold = null
  alignStub.throws = null
})

// ==================== bootstrap ====================

describe('bootstrap', () => {
  it('argv 是 bootstrap --version v<应用版本>，且没有对应物的三段立刻置完成', async () => {
    const updates: BootstrapProgressUpdate[] = []
    FakeRuntimeClient.scripts = [
      { events: fixtureEvents('bootstrap-success.ndjson') as RuntimeEvent[] },
    ]

    const outcome = await createService().bootstrap(update => updates.push(update))

    expect(outcome.success).toBe(true)
    expect(FakeRuntimeClient.calls).toHaveLength(1)
    expect(FakeRuntimeClient.calls[0].command).toEqual(['bootstrap', '--version', 'v5.5.0-beta.3'])
    expect(FakeRuntimeClient.calls[0].mirrors).toEqual([])

    for (const stage of ['mirror', 'pip', 'git'] as const) {
      const takeover = updates.filter(u => u.stage === stage)
      expect(takeover).toHaveLength(1)
      expect(takeover[0]).toMatchObject({ status: 'completed', message: RUNTIME_TAKEOVER_MESSAGE })
    }

    for (const stage of ['python', 'repository', 'dependency'] as const) {
      const statuses = updates.filter(u => u.stage === stage).map(u => u.status)
      expect(statuses[0]).toBe('started')
      expect(statuses[statuses.length - 1]).toBe('completed')
    }
  })

  it('依赖同步失败时失败段是 dependency，结构化字段与日志整块透传', async () => {
    const operationId = base.operationId
    FakeRuntimeClient.scripts = [
      {
        events: [
          helloEvent,
          {
            ...base,
            type: 'log',
            sequence: 2,
            source: 'runtime',
            stream: 'stdout',
            message: 'Resolved 120 packages',
          },
          {
            ...base,
            type: 'log',
            sequence: 3,
            source: 'runtime',
            stream: 'stderr',
            message: 'error: distribution not found',
          },
          {
            ...base,
            type: 'error',
            sequence: 4,
            code: 'DEPENDENCY_SYNC_FAILED',
            stage: 'dependencies.sync',
            message: 'Python 依赖安装失败',
            retryable: true,
            remediation: ['retry', 'switch-mirror', 'rebuild-environment'],
            details: { operationId },
          },
          {
            ...base,
            type: 'result',
            sequence: 5,
            success: false,
            code: 'DEPENDENCY_SYNC_FAILED',
            // result 上带的是顶层 stage，失败段必须取主错误事件的 stage
            stage: 'bootstrap',
            status: 'environment_broken',
            message: 'Python 依赖同步失败',
            retryable: true,
            remediation: ['retry', 'switch-mirror', 'rebuild-environment'],
            details: {},
          },
        ] as unknown as RuntimeEvent[],
      },
    ]

    const updates: BootstrapProgressUpdate[] = []
    const outcome = await createService().bootstrap(update => updates.push(update))

    expect(outcome.success).toBe(false)
    expect(outcome.failedStage).toBe('dependency')
    expect(outcome.code).toBe('DEPENDENCY_SYNC_FAILED')
    expect(outcome.retryable).toBe(true)
    expect(outcome.remediation).toEqual(['retry', 'switch-mirror', 'rebuild-environment'])
    expect(outcome.logs).toContain('[stdout]')
    expect(outcome.logs).toContain('Resolved 120 packages')
    expect(outcome.logs).toContain('[stderr]')
    expect(outcome.logs).toContain('error: distribution not found')
    expect(updates[updates.length - 1]).toMatchObject({ stage: 'dependency', status: 'failed' })
  })
})

// ==================== 第 0 步：Runtime 对齐 ====================

describe('第 0 步：bootstrap 之前先对齐 Runtime', () => {
  it('按目标版本的发布通道、当前 exe 与 app-root 调用对齐，且在 bootstrap 命令之前', async () => {
    const order: string[] = []
    alignStub.result = {
      status: 'upgraded',
      target: { version: 'v0.1.10' },
      targetSource: 'cnb',
    }
    const service = new RuntimeInitializationService({
      launchConfig: {
        mode: 'managed',
        runtimePath: RUNTIME_PATH,
        appRoot: APP_ROOT,
        dataRoot: APP_ROOT,
      },
      mirrorService: fakeMirrorService(),
      createClient: options => {
        order.push('client')
        return new FakeRuntimeClient(options) as never
      },
      alignRuntimeBinary: async options => {
        order.push('align')
        return alignStub.run(options)
      },
    })

    const outcome = await service.bootstrap(() => undefined)

    expect(outcome.success).toBe(true)
    expect(order).toEqual(['align', 'client'])
    expect(alignStub.calls).toHaveLength(1)
    expect(alignStub.calls[0]).toMatchObject({
      channel: 'prerelease',
      runtimePath: RUNTIME_PATH,
      appRoot: APP_ROOT,
    })
    expect(FakeRuntimeClient.calls[0].command).toEqual(['bootstrap', '--version', 'v5.5.0-beta.3'])
  })

  it('第 0 步失败时不跑 bootstrap：失败段是运行环境、可重试、给重试与打开日志', async () => {
    const updates: BootstrapProgressUpdate[] = []
    alignStub.result = {
      status: 'failed',
      code: RUNTIME_LATEST_UNAVAILABLE,
      error: '无法确认线上最新的 Runtime 版本：CNB 与 GitHub 都没有给出结果',
    }

    const outcome = await createService().bootstrap(update => updates.push(update))

    expect(outcome).toEqual({
      success: false,
      error: '无法确认线上最新的 Runtime 版本：CNB 与 GitHub 都没有给出结果',
      code: RUNTIME_LATEST_UNAVAILABLE,
      retryable: true,
      remediation: ['retry', 'open-log'],
      failedStage: 'python',
      failureOrigin: 'runtime_binary',
    })
    expect(FakeRuntimeClient.calls).toHaveLength(0)
    expect(updates.at(-1)).toMatchObject({
      stage: 'python',
      status: 'failed',
      message: outcome.error,
    })
  })

  it('解析不到最新版且网络不可用时退回 bootstrap --if-needed 复用本地环境', async () => {
    const updates: BootstrapProgressUpdate[] = []
    alignStub.result = {
      status: 'failed',
      code: RUNTIME_LATEST_UNAVAILABLE,
      error: '无法确认线上最新的 Runtime 版本：CNB 与 GitHub 都没有给出结果',
      networkUnavailable: true,
    }

    const outcome = await createService().bootstrap(update => updates.push(update))

    expect(outcome.success).toBe(true)
    expect(FakeRuntimeClient.calls[0].command).toEqual([
      'bootstrap',
      '--version',
      'v5.5.0-beta.3',
      '--if-needed',
    ])
    expect(
      updates.find(update => update.message === '网络不可用，跳过更新检查，正在检查本地运行环境')
    ).toBeDefined()
  })

  it('第 0 步期间 cancel() 生效：对齐看到取消判据，结果是 OPERATION_CANCELLED 且不跑 bootstrap', async () => {
    let release: (() => void) | undefined
    alignStub.hold = new Promise(resolve => {
      release = resolve
    })
    const service = createService()
    let observedCancel: boolean | undefined
    alignStub.result = { status: 'cancelled', code: RUNTIME_BINARY_CANCELLED }

    const pending = service.bootstrap(() => undefined)
    await vi.waitFor(() => expect(alignStub.calls).toHaveLength(1))
    expect(service.cancel()).toBe(true)
    observedCancel = alignStub.calls[0].isCancelled?.()
    release?.()
    const outcome = await pending

    expect(observedCancel).toBe(true)
    expect(outcome.success).toBe(false)
    expect(outcome.code).toBe(RUNTIME_BINARY_CANCELLED)
    expect(outcome.failureOrigin).toBe('runtime_binary')
    expect(FakeRuntimeClient.calls).toHaveLength(0)
  })
})

// ==================== 单步重试 ====================

describe('单步重试', () => {
  it('运行环境重试的 Runtime 对齐失败保留实际来源和界面失败段', async () => {
    alignStub.result = {
      status: 'failed',
      code: RUNTIME_LATEST_UNAVAILABLE,
      error: '无法确认线上最新的 Runtime 版本',
    }

    const outcome = await createService().retryStage('python', () => undefined)

    expect(outcome).toMatchObject({
      success: false,
      failedStage: 'python',
      failureOrigin: 'runtime_binary',
    })
    expect(FakeRuntimeClient.calls).toHaveLength(0)
  })

  it('依赖段重试走 dependencies sync', async () => {
    FakeRuntimeClient.scripts = [{ events: [helloEvent, okResult('dependencies.sync')] }]

    const outcome = await createService().retryStage('dependency', () => undefined)

    expect(outcome.success).toBe(true)
    expect(FakeRuntimeClient.calls[0].command).toEqual(['dependencies', 'sync'])
  })
})
