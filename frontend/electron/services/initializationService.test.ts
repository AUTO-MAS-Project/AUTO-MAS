import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { InitializationService, InitializationProgress } from './initializationService'
import { RUNTIME_EXE_ENV, RUNTIME_MODE_ENV } from './runtime'
import type { RuntimeEvent, RuntimeRunOptions } from './runtime'

// ==================== 旧链路各服务的桩 ====================

const installCalls: string[] = []

function installerStub(name: string) {
  return class {
    async install(onProgress?: (progress: unknown) => void) {
      installCalls.push(name)
      onProgress?.({ progress: 100, message: `${name} 完成` })
      return { success: true }
    }
  }
}

vi.mock('./mirrorService', () => ({
  MirrorService: class {
    async initialize() {
      installCalls.push('mirror')
    }
  },
}))
vi.mock('./environmentService', () => ({
  PythonInstaller: installerStub('python'),
  PipInstaller: installerStub('pip'),
  GitInstaller: installerStub('git'),
}))
vi.mock('./repositoryService', () => ({
  RepositoryService: class {
    async pullRepository(onProgress?: (progress: unknown) => void) {
      installCalls.push('repository')
      onProgress?.({ progress: 100, message: '源码拉取完成' })
      return { success: true }
    }
  },
}))
vi.mock('./dependencyService', () => ({
  DependencyService: class {
    async installDependencies(onProgress?: (progress: unknown) => void) {
      installCalls.push('dependency')
      onProgress?.({ progress: 100, message: '依赖安装完成' })
      return { success: true }
    }
  },
}))
vi.mock('./backendService', () => ({
  BackendService: class {
    async startBackend() {
      installCalls.push('backend')
      return { success: true }
    }
    getStatus() {
      return { isRunning: true, pid: 4242 }
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
vi.mock('electron', () => ({ app: { getVersion: () => '5.5.0-beta.3' } }))

// ==================== 假 RuntimeClient ====================

const base = {
  protocol: 1,
  operationId: '01M1F6M33JFZZ7Y85BE5S849ZN',
  timestamp: '2026-09-01T22:03:00.000+02:00',
}

const bootstrapEvents = [
  {
    ...base,
    type: 'hello',
    sequence: 1,
    runtimeVersion: 'dev',
    command: 'bootstrap',
    capabilities: [],
  },
  {
    ...base,
    type: 'state',
    sequence: 2,
    stage: 'uv.check',
    status: 'preparing_uv',
    message: '正在准备固定版本 uv',
    details: {},
  },
  {
    ...base,
    type: 'state',
    sequence: 3,
    stage: 'workspace.check',
    status: 'syncing_repository',
    message: '正在同步后端仓库',
    details: {},
  },
  {
    ...base,
    type: 'state',
    sequence: 4,
    stage: 'dependencies.sync',
    status: 'syncing_environment',
    message: '正在同步锁定依赖',
    details: {},
  },
  {
    ...base,
    type: 'result',
    sequence: 5,
    success: true,
    code: 'OK',
    stage: 'bootstrap',
    status: 'ready_to_start',
    message: '运行环境准备完成',
    retryable: false,
    remediation: [],
    details: {},
  },
] as unknown as RuntimeEvent[]

const { runtimeClientCalls } = vi.hoisted(() => ({ runtimeClientCalls: [] as string[][] }))

vi.mock('./runtime', async importActual => {
  const actual = await importActual<typeof import('./runtime')>()

  // 假客户端必须定义在工厂里：vi.mock 会被提升到文件顶部，引用外层变量会踩到 TDZ。
  class FakeRuntimeClient {
    constructor(readonly options: { runtimePath: string; appRoot: string }) {}

    async run(command: string[], options: RuntimeRunOptions = {}) {
      runtimeClientCalls.push(command)
      for (const event of bootstrapEvents) {
        if (event.type === 'state') options.onState?.(event)
      }
      const result = bootstrapEvents[bootstrapEvents.length - 1]
      return {
        hello: bootstrapEvents[0],
        result,
        success: true,
        code: 'OK',
        events: bootstrapEvents,
        warnings: [],
        errors: [],
        logs: {},
        protocolErrors: [],
        exitCode: 0,
        signal: null,
        stderr: '',
        argv: command,
        durationMs: 1,
      }
    }
  }

  return { ...actual, RuntimeClient: FakeRuntimeClient }
})

// runtimeInitializationService.ts 的默认客户端工厂现在经 createRuntimeClient（见
// runtime/runtimeClientFactory.ts）统一注入遥测环境变量，它从 './client'（相对
// runtime/ 目录，即 './runtime/client'）直接拿 RuntimeClient，不经过上面这层
// './runtime' 桶文件的重导出。只替身 './runtime' 拦不到这次真实构造，这里必须把
// 同一个假类也接到 './runtime/client' 上，否则会去 spawn 一个真的子进程。
vi.mock('./runtime/client', async importActual => {
  const actual = await importActual<typeof import('./runtime/client')>()

  class FakeRuntimeClient {
    constructor(readonly options: { runtimePath: string; appRoot: string }) {}

    async run(command: string[], options: RuntimeRunOptions = {}) {
      runtimeClientCalls.push(command)
      for (const event of bootstrapEvents) {
        if (event.type === 'state') options.onState?.(event)
      }
      const result = bootstrapEvents[bootstrapEvents.length - 1]
      return {
        hello: bootstrapEvents[0],
        result,
        success: true,
        code: 'OK',
        events: bootstrapEvents,
        warnings: [],
        errors: [],
        logs: {},
        protocolErrors: [],
        exitCode: 0,
        signal: null,
        stderr: '',
        argv: command,
        durationMs: 1,
      }
    }
  }

  return { ...actual, RuntimeClient: FakeRuntimeClient }
})

// ==================== 用例 ====================

const APP_ROOT = 'D:\\AUTO-MAS'
// 灰度开关要求 Runtime 可执行文件真实存在，借用一定存在的 node 自身路径。
const EXISTING_EXE = process.execPath

function collect(): {
  progress: InitializationProgress[]
  onProgress: (p: InitializationProgress) => void
} {
  const progress: InitializationProgress[] = []
  return { progress, onProgress: p => progress.push(p) }
}

beforeEach(() => {
  installCalls.length = 0
  runtimeClientCalls.length = 0
  delete process.env[RUNTIME_MODE_ENV]
  delete process.env[RUNTIME_EXE_ENV]
})

afterEach(() => {
  delete process.env[RUNTIME_MODE_ENV]
  delete process.env[RUNTIME_EXE_ENV]
})

describe('灰度开关关闭时', () => {
  it('initialize 仍逐段调用旧链路，且不构造 Runtime 客户端', async () => {
    const { progress, onProgress } = collect()

    const result = await new InitializationService(APP_ROOT).initialize(onProgress)

    expect(result.success).toBe(true)
    expect(installCalls).toEqual([
      'mirror',
      'python',
      'pip',
      'git',
      'repository',
      'dependency',
      'backend',
    ])
    expect(runtimeClientCalls).toHaveLength(0)
    // 旧链路不产生段状态与结构化结果码
    expect(progress.every(p => p.status === undefined)).toBe(true)
    expect(result.code).toBeUndefined()
  })
})

describe('development 模式', () => {
  beforeEach(() => {
    process.env[RUNTIME_MODE_ENV] = 'development'
    process.env[RUNTIME_EXE_ENV] = EXISTING_EXE
  })

  it('六个准备段各收到一个完成进度，随后进入 backend 段', async () => {
    const { progress, onProgress } = collect()

    const result = await new InitializationService(APP_ROOT).initialize(onProgress)

    expect(result.success).toBe(true)
    expect(result.completedStages).toContain('backend')
    // 一个安装器都没跑，只起了后端
    expect(installCalls).toEqual(['backend'])
    expect(runtimeClientCalls).toHaveLength(0)

    const skipped = progress.filter(p => p.message === '由 Runtime development 模式接管，跳过')
    expect(skipped.map(p => p.stage)).toEqual([
      'mirror',
      'python',
      'pip',
      'git',
      'repository',
      'dependency',
    ])
    expect(skipped.every(p => p.status === 'completed' && p.progress === 100)).toBe(true)

    expect(progress.filter(p => p.stage === 'backend').map(p => p.status)).toEqual([
      'started',
      'completed',
    ])
    expect(progress[progress.length - 1].stage).toBe('complete')
  })
})

describe('managed 模式', () => {
  beforeEach(() => {
    process.env[RUNTIME_MODE_ENV] = 'managed'
    process.env[RUNTIME_EXE_ENV] = EXISTING_EXE
  })

  it('一次 bootstrap 顶掉五步安装链，段序为三段 started→completed 后进 backend', async () => {
    const { progress, onProgress } = collect()

    const result = await new InitializationService(APP_ROOT).initialize(onProgress)

    expect(result.success).toBe(true)
    expect(runtimeClientCalls).toEqual([['bootstrap', '--version', 'v5.5.0-beta.3']])
    expect(installCalls).toEqual(['backend'])

    for (const stage of ['mirror', 'pip', 'git'] as const) {
      const takeover = progress.filter(p => p.stage === stage)
      expect(takeover).toHaveLength(1)
      expect(takeover[0]).toMatchObject({ status: 'completed', message: '由 Runtime 接管' })
    }

    for (const stage of ['python', 'repository', 'dependency'] as const) {
      const statuses = progress.filter(p => p.stage === stage).map(p => p.status)
      expect(statuses[0]).toBe('started')
      expect(statuses[statuses.length - 1]).toBe('completed')
    }

    expect(progress.filter(p => p.stage === 'backend').map(p => p.status)).toEqual([
      'started',
      'completed',
    ])
    expect(progress[progress.length - 1].stage).toBe('complete')
  })

  it('找不到 Runtime 可执行文件时按 RUNTIME_NOT_FOUND 失败，不回退旧链路', async () => {
    delete process.env[RUNTIME_EXE_ENV]

    const result = await new InitializationService(APP_ROOT).initialize(() => undefined)

    expect(result.success).toBe(false)
    expect(result.code).toBe('RUNTIME_NOT_FOUND')
    expect(installCalls).toEqual([])
  })
})
