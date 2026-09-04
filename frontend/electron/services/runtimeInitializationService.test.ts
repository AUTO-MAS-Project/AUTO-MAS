import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import {
  BootstrapProgressBridge,
  BootstrapProgressUpdate,
  MirrorLookup,
  RUNTIME_TAKEOVER_MESSAGE,
  RuntimeInitializationService,
  emitDevelopmentSkipProgress,
  mapDoctorChecksToCriticalFiles,
  mapMirrorSelection,
  mapRuntimeStage,
  mapRuntimeStageToInitializationStage,
  toRuntimeVersion,
} from './runtimeInitializationService'
import type {
  CreateRuntimeClientOptions,
  RuntimeEvent,
  RuntimeRunOptions,
  RuntimeSupervisedLaunchConfig,
} from './runtime'
import type { MirrorConfig, MirrorSource } from './mirrorService'

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
})

// ==================== 阶段映射 ====================

describe('阶段映射', () => {
  it('uv 与 python 都落在 python 段，仓库与依赖各自成段', () => {
    expect(mapRuntimeStage('uv.check')).toBe('python')
    expect(mapRuntimeStage('uv.download')).toBe('python')
    expect(mapRuntimeStage('uv.verify')).toBe('python')
    expect(mapRuntimeStage('python.check')).toBe('python')
    expect(mapRuntimeStage('python.install')).toBe('python')
    expect(mapRuntimeStage('workspace.clone')).toBe('repository')
    expect(mapRuntimeStage('workspace.swap')).toBe('repository')
    expect(mapRuntimeStage('dependencies.sync')).toBe('dependency')
    expect(mapRuntimeStage('dependencies.rebuild')).toBe('dependency')
    expect(mapRuntimeStage('backend.health')).toBe('backend')
  })

  it('未知 stage 落到通用段而不是抛错', () => {
    expect(() => mapRuntimeStage('quantum.entangle')).not.toThrow()
    expect(mapRuntimeStage('quantum.entangle')).toBe('python')
    expect(mapRuntimeStage('bootstrap')).toBe('python')
    expect(mapRuntimeStageToInitializationStage('bootstrap')).toBeNull()
    expect(mapRuntimeStageToInitializationStage('quantum.entangle')).toBeNull()
  })

  it('真实 bootstrap 事件流里的每个 stage 都有显式对应', () => {
    const stages = new Set<string>()
    for (const event of fixtureEvents('bootstrap-success.ndjson')) {
      if ('stage' in event && typeof event.stage === 'string') stages.add(event.stage)
    }

    // 顶层 result 用的 `bootstrap` 本来就没有对应的界面段，其余必须全部命中。
    const unmapped = [...stages].filter(
      stage => mapRuntimeStageToInitializationStage(stage) === null
    )
    expect(unmapped).toEqual(['bootstrap'])
    expect(stages).toContain('dependencies.sync')
    expect(stages).toContain('workspace.clone')
  })
})

describe('目标版本', () => {
  it('补齐 Runtime 要求的 v 前缀', () => {
    expect(toRuntimeVersion('5.5.0-beta.3')).toBe('v5.5.0-beta.3')
    expect(toRuntimeVersion('v5.5.0-beta.3')).toBe('v5.5.0-beta.3')
  })
})

describe('镜像源映射', () => {
  it('选中值本来就是 key 时按 key 解析，只映射语义对得上的键，其余返回 null', () => {
    const mirrors = fakeMirrorService()
    expect(mapMirrorSelection(mirrors, 'repository', 'cnb')).toEqual({ kind: 'git', key: 'cnb' })
    expect(mapMirrorSelection(mirrors, 'repository', 'github')).toEqual({
      kind: 'git',
      key: 'github',
    })
    expect(mapMirrorSelection(mirrors, 'python', 'official')).toEqual({
      kind: 'python',
      key: 'github',
    })

    // Runtime 的 git 目录里没有这些源
    expect(mapMirrorSelection(mirrors, 'repository', 'ghproxy_edgeone')).toBeNull()
    expect(mapMirrorSelection(mirrors, 'repository', 'ghfast')).toBeNull()
    // 旧 python 类是 python.org 分发源，其余键在 Runtime 里没有对应物
    expect(mapMirrorSelection(mirrors, 'python', 'aliyun')).toBeNull()
    // official 对应 Runtime 的 pypi，键名对不上，不映射
    expect(mapMirrorSelection(mirrors, 'dependency', 'official')).toBeNull()
    expect(mapMirrorSelection(mirrors, 'git', 'autonas')).toBeNull()
    expect(mapMirrorSelection(mirrors, 'repository', '')).toBeNull()
  })

  it('选中值是旧链路存的 name 时也能解析——渲染进程存进 state.selectedMirror 的就是 name', () => {
    const mirrors = fakeMirrorService()
    // MirrorRotationService.execute(..., preferredMirrorName) 按 mirror.name 匹配；
    // 用 name 或用 key 解析到同一个 MirrorSource，映射结果应当一致
    expect(mapMirrorSelection(mirrors, 'repository', 'CNB 官方镜像')).toEqual({
      kind: 'git',
      key: 'cnb',
    })
    expect(mapMirrorSelection(mirrors, 'python', 'Python 官方')).toEqual({
      kind: 'python',
      key: 'github',
    })
  })

  it('旧镜像列表里根本找不到这个选中值时返回 null', () => {
    const mirrors = fakeMirrorService()
    expect(mapMirrorSelection(mirrors, 'repository', '不存在的镜像')).toBeNull()
    expect(mapMirrorSelection(mirrors, 'dependency', 'unknown-key')).toBeNull()
  })

  it('T13.4 起 dependency 段可以传 package-index，但只映射键名相同的三项', () => {
    const mirrors = fakeMirrorService()
    expect(mapMirrorSelection(mirrors, 'dependency', 'aliyun')).toEqual({
      kind: 'package-index',
      key: 'aliyun',
    })
    expect(mapMirrorSelection(mirrors, 'dependency', 'tsinghua')).toEqual({
      kind: 'package-index',
      key: 'tsinghua',
    })
    expect(mapMirrorSelection(mirrors, 'dependency', 'ustc')).toEqual({
      kind: 'package-index',
      key: 'ustc',
    })
    // 用 name 选中同样生效
    expect(mapMirrorSelection(mirrors, 'dependency', '清华大学')).toEqual({
      kind: 'package-index',
      key: 'tsinghua',
    })
  })
})

// ==================== 进度桥接 ====================

describe('进度桥接', () => {
  it('回放真实事件流时三段各出现一次 started 与 completed，且段序不倒退', () => {
    const updates: BootstrapProgressUpdate[] = []
    const bridge = new BootstrapProgressBridge(update => updates.push(update))
    bridge.takeOver()

    for (const event of fixtureEvents('bootstrap-success.ndjson')) {
      if (event.type === 'progress') bridge.observe(event.stage, event.message, event.percent)
      if (event.type === 'state') bridge.observe(event.stage, event.message)
    }
    bridge.finish('运行环境准备完成')

    const started = updates.filter(u => u.status === 'started').map(u => u.stage)
    expect(started).toEqual(['python', 'repository', 'dependency'])

    for (const stage of ['python', 'repository', 'dependency'] as const) {
      expect(updates.filter(u => u.stage === stage && u.status === 'completed')).toHaveLength(1)
    }

    // 真实顺序是 uv → 仓库 → Python → 依赖，python.* 落在仓库之后也不能把段拉回去
    const pythonInstall = updates.find(u => u.message === '正在准备受管 Python')
    expect(pythonInstall?.stage).toBe('repository')
  })

  it('没有 percent 时段内停在 10%，段结束才 100%', () => {
    const updates: BootstrapProgressUpdate[] = []
    const bridge = new BootstrapProgressBridge(update => updates.push(update))

    bridge.observe('uv.download', '正在准备固定版本 uv')
    bridge.observe('uv.verify', '固定版本 uv 已校验')
    expect(updates.map(u => u.progress)).toEqual([10, 10])

    bridge.observe('workspace.clone', '正在同步后端仓库', 42.86)
    bridge.observe('workspace.clone', '正在接收后端仓库数据', 63.4)
    expect(updates[2]).toMatchObject({ stage: 'python', status: 'completed', progress: 100 })
    expect(updates[3]).toMatchObject({ stage: 'repository', status: 'started', progress: 10 })
    expect(updates[4]).toMatchObject({ stage: 'repository', status: 'running', progress: 63 })
  })

  it('还没进过任何段时不会顺手把前面的段报成完成', () => {
    const updates: BootstrapProgressUpdate[] = []
    const bridge = new BootstrapProgressBridge(update => updates.push(update))

    bridge.observe('dependencies.sync', '正在同步锁定依赖')
    expect(updates).toEqual([
      { stage: 'dependency', status: 'started', progress: 10, message: '正在同步锁定依赖' },
    ])
  })
})

describe('development 模式跳过', () => {
  it('六个准备段各发一个完成', () => {
    const updates: BootstrapProgressUpdate[] = []
    emitDevelopmentSkipProgress(update => updates.push(update))

    expect(updates.map(u => u.stage)).toEqual([
      'mirror',
      'python',
      'pip',
      'git',
      'repository',
      'dependency',
    ])
    expect(updates.every(u => u.status === 'completed' && u.progress === 100)).toBe(true)
    expect(updates[0].message).toBe('由 Runtime development 模式接管，跳过')
  })
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

  it('找不到可执行文件时按 RUNTIME_NOT_FOUND 失败，不构造客户端', async () => {
    const outcome = await createService({ runtimePath: null }).bootstrap(() => undefined)

    expect(outcome.success).toBe(false)
    expect(outcome.code).toBe('RUNTIME_NOT_FOUND')
    expect(outcome.retryable).toBe(false)
    expect(FakeRuntimeClient.calls).toHaveLength(0)
  })
})

// ==================== 单步重试 ====================

describe('单步重试', () => {
  it('依赖段重试走 dependencies sync', async () => {
    FakeRuntimeClient.scripts = [{ events: [helloEvent, okResult('dependencies.sync')] }]

    const outcome = await createService().retryStage('dependency', () => undefined)

    expect(outcome.success).toBe(true)
    expect(FakeRuntimeClient.calls[0].command).toEqual(['dependencies', 'sync'])
  })

  it('上一次失败要求重建环境时依赖段改走 dependencies rebuild', async () => {
    const service = createService()
    FakeRuntimeClient.scripts = [
      {
        events: [
          helloEvent,
          {
            ...base,
            type: 'result',
            sequence: 5,
            success: false,
            code: 'DEPENDENCY_SYNC_FAILED',
            stage: 'dependencies.sync',
            status: 'environment_broken',
            message: 'Python 依赖同步失败',
            retryable: true,
            remediation: ['retry-sync', 'rebuild-environment', 'open-log'],
            details: {},
          },
        ] as unknown as RuntimeEvent[],
      },
      { events: [helloEvent, okResult('dependencies.rebuild')] },
    ]

    await service.bootstrap(() => undefined)
    const outcome = await service.retryStage('dependency', () => undefined)

    expect(outcome.success).toBe(true)
    expect(FakeRuntimeClient.calls[1].command).toEqual(['dependencies', 'rebuild'])
  })

  it('python 段重试走 environment ensure，要求重建环境时走 repair', async () => {
    const service = createService()
    FakeRuntimeClient.scripts = [{ events: [helloEvent, okResult('uv.check')] }]
    await service.retryStage('python', () => undefined)
    expect(FakeRuntimeClient.calls[0].command).toEqual(['environment', 'ensure'])

    FakeRuntimeClient.scripts = [
      {
        events: [
          helloEvent,
          {
            ...base,
            type: 'result',
            sequence: 4,
            success: false,
            code: 'PYTHON_VERSION_MISMATCH',
            stage: 'python.check',
            status: 'environment_broken',
            message: '环境内 Python 版本与目标不一致',
            retryable: true,
            remediation: ['rebuild-environment'],
            details: {},
          },
        ] as unknown as RuntimeEvent[],
      },
      { events: [helloEvent, okResult('repair')] },
    ]
    FakeRuntimeClient.calls = []
    await service.bootstrap(() => undefined)
    await service.retryStage('python', () => undefined)
    expect(FakeRuntimeClient.calls[1].command).toEqual(['repair'])
  })

  it('仓库段重试走 workspace sync --version', async () => {
    FakeRuntimeClient.scripts = [{ events: [helloEvent, okResult('workspace.clone')] }]

    await createService().retryStage('repository', () => undefined)

    expect(FakeRuntimeClient.calls[0].command).toEqual([
      'workspace',
      'sync',
      '--version',
      'v5.5.0-beta.3',
    ])
  })

  it('切换镜像后整条 bootstrap 重跑并带上 --mirror', async () => {
    FakeRuntimeClient.scripts = [{ events: [helloEvent, okResult('bootstrap')] }]

    await createService().retryStage('repository', () => undefined, 'cnb')

    expect(FakeRuntimeClient.calls[0].command).toEqual(['bootstrap', '--version', 'v5.5.0-beta.3'])
    expect(FakeRuntimeClient.calls[0].mirrors).toEqual([{ kind: 'git', key: 'cnb' }])
  })

  it('镜像键映射不到时仍重跑 bootstrap 但不传 --mirror', async () => {
    FakeRuntimeClient.scripts = [{ events: [helloEvent, okResult('bootstrap')] }]

    // official 在 pip_mirror 里能解析到，但键名对不上 Runtime 的 pypi，映射表里没有它
    await createService().retryStage('dependency', () => undefined, 'official')

    expect(FakeRuntimeClient.calls[0].command[0]).toBe('bootstrap')
    expect(FakeRuntimeClient.calls[0].mirrors).toEqual([])
  })

  it('mirror / pip / git 三段直接按成功返回，不启动 Runtime', async () => {
    const service = createService()
    const updates: BootstrapProgressUpdate[] = []

    for (const stage of ['mirror', 'pip', 'git'] as const) {
      const outcome = await service.retryStage(stage, update => updates.push(update))
      expect(outcome.success).toBe(true)
    }

    expect(FakeRuntimeClient.calls).toHaveLength(0)
    expect(updates.map(u => u.stage)).toEqual(['mirror', 'pip', 'git'])
  })
})

// ==================== doctor ====================

describe('doctor', () => {
  it('layout.repo 缺失映射成需要初始化', async () => {
    FakeRuntimeClient.scripts = [{ events: fixtureEvents('doctor.ndjson') as RuntimeEvent[] }]

    const checks = await createService().doctor()
    expect(checks).toBeDefined()
    expect(FakeRuntimeClient.calls[0].command).toEqual(['doctor'])

    const critical = mapDoctorChecksToCriticalFiles(checks ?? [])
    expect(critical.mainPyExists).toBe(false)
    expect(critical.pythonExists).toBe(false)
    // 新链路不装 pip、不装 Git，这两项不参与判定
    expect(critical.pipExists).toBe(true)
    expect(critical.gitExists).toBe(true)
  })

  it('layout.repo 就绪时不再要求初始化', () => {
    const critical = mapDoctorChecksToCriticalFiles([
      { id: 'layout', name: '受管目录布局', message: '', status: 'ok', details: { repo: 'ok' } },
      { id: 'python', name: '受管 Python', message: '', status: 'ok', details: {} },
    ])

    expect(critical.mainPyExists).toBe(true)
    expect(critical.pythonExists).toBe(true)
  })
})

// ==================== 客户端构造参数 ====================

describe('客户端构造参数', () => {
  it('把 dataRoot 与启动模式一并交给客户端工厂，--app-root 仍是 Runtime 根目录', async () => {
    const received: CreateRuntimeClientOptions[] = []
    const service = new RuntimeInitializationService({
      launchConfig: {
        mode: 'development',
        runtimePath: RUNTIME_PATH,
        appRoot: 'D:\\AUTO-MAS-runtime',
        repo: APP_ROOT,
        dataRoot: APP_ROOT,
      },
      mirrorService: fakeMirrorService(),
      createClient: options => {
        received.push(options)
        return new FakeRuntimeClient(options) as never
      },
    })
    FakeRuntimeClient.scripts = [{ events: fixtureEvents('doctor.ndjson') }]

    await service.doctor()

    expect(received).toHaveLength(1)
    expect(received[0]).toMatchObject({
      runtimePath: RUNTIME_PATH,
      appRoot: 'D:\\AUTO-MAS-runtime',
      dataRoot: APP_ROOT,
      launchMode: 'development',
    })
  })
})
