import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import {
  BootstrapProgressBridge,
  BootstrapProgressUpdate,
  MirrorLookup,
  NETWORK_PROBE_STAGE,
  RUNTIME_BINARY_CHECK_STAGE,
  RUNTIME_BINARY_DOWNLOAD_STAGE,
  RUNTIME_TAKEOVER_MESSAGE,
  RuntimeInitializationService,
  describeRuntimeFailureDetails,
  emitDevelopmentSkipProgress,
  mapDoctorChecksToCriticalFiles,
  mapMirrorSelection,
  mapRuntimeStage,
  mapRuntimeStageToInitializationStage,
  resolveProgressPercent,
  toRuntimeVersion,
} from './runtimeInitializationService'
import type {
  CreateRuntimeClientOptions,
  RuntimeEvent,
  RuntimeRunOptions,
  RuntimeSupervisedLaunchConfig,
} from './runtime'
import type { MirrorConfig, MirrorSource } from './mirrorService'
import {
  RUNTIME_BINARY_CANCELLED,
  RUNTIME_PIN_UNAVAILABLE,
  type RuntimeBinaryAlignOptions,
  type RuntimeBinaryAlignResult,
} from './runtimeBinaryService'

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

/**
 * 夹具由本机构建的 auto-mas-runtime.exe 真实跑出来，不是手写的。
 * 例外：`bootstrap-network-relay.ndjson` 按 2026-09-11 M14 构建的真机样本裁剪重写，事件顺序、
 * 数值形态照真机；git 类源的测速按修订后契约不带 bytesPerSecond。
 */
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
  result: { status: 'current', pin: { version: 'v0.1.7' } } as RuntimeBinaryAlignResult,
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
  alignStub.result = { status: 'current', pin: { version: 'v0.1.7' } }
  alignStub.hold = null
  alignStub.throws = null
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

  it('M14 事件流里只有测速 stage 与顶层 bootstrap 没有显式对应，测速走通用段不抛错', () => {
    const stages = new Set<string>()
    for (const event of fixtureEvents('bootstrap-network-relay.ndjson')) {
      if ('stage' in event && typeof event.stage === 'string') stages.add(event.stage)
    }

    const unmapped = [...stages]
      .filter(stage => mapRuntimeStageToInitializationStage(stage) === null)
      .sort()
    expect(unmapped).toEqual(['bootstrap', NETWORK_PROBE_STAGE])
    expect(mapRuntimeStage(NETWORK_PROBE_STAGE)).toBe('python')
  })
})

describe('失败 details 摘要', () => {
  it('没有可打的键时返回空串', () => {
    expect(describeRuntimeFailureDetails({})).toBe('')
  })

  // UPDATE_STATE_AMBIGUOUS 在 Runtime 侧有二十来个抛出点，只有 reason 分得清是哪一个。
  it('保留 reason 这类定位字段', () => {
    expect(describeRuntimeFailureDetails({ reason: 'prepared_update_missing' })).toBe(
      ' details={"reason":"prepared_update_missing"}'
    )
  })

  it('logPath / stderr / checks 已由别处取用，不重复进这一行', () => {
    expect(
      describeRuntimeFailureDetails({
        logPath: 'D:\\AUTO-MAS\\logs\\runtime\\bootstrap.log',
        stderr: 'No pyvenv.cfg file',
        checks: [{ id: 'venv' }],
      })
    ).toBe('')
  })

  it('保留镜像轮换的 attempts', () => {
    const text = describeRuntimeFailureDetails({
      attempts: [{ source: 'cnb', outcome: 'switch_source', failureKind: 'branch_missing' }],
    })
    expect(text).toContain('cnb')
    expect(text).toContain('branch_missing')
  })

  it('超长 details 截断而不是整条塞进日志', () => {
    const text = describeRuntimeFailureDetails({ blob: 'x'.repeat(5000) })
    expect(text.length).toBeLessThan(1100)
    expect(text).toContain('已截断')
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
    // 段开始时带着真实百分比就照发（#570 起的既有行为，当时没同步这条期望值）
    expect(updates[3]).toMatchObject({ stage: 'repository', status: 'started', progress: 43 })
    expect(updates[4]).toMatchObject({ stage: 'repository', status: 'running', progress: 63 })
  })

  it('还没进过任何段时不会顺手把前面的段报成完成', () => {
    const updates: BootstrapProgressUpdate[] = []
    const bridge = new BootstrapProgressBridge(update => updates.push(update))

    bridge.observe('dependencies.sync', '正在同步锁定依赖')
    expect(updates).toEqual([
      {
        stage: 'dependency',
        status: 'started',
        progress: 10,
        message: '正在同步锁定依赖',
        indeterminate: true,
        runtimeStage: 'dependencies.sync',
      },
    ])
  })

  /**
   * 一个界面段里装着好几个 Runtime stage（uv.download 之后还有校验、解压、python.*），
   * 所以 100 只能由段收口发出；running 途中不得让渲染层看到 100，段内也不得倒退。
   */
  function expectStageMonotonicAndClosedOnce(
    updates: BootstrapProgressUpdate[],
    stage: BootstrapProgressUpdate['stage']
  ): void {
    const inStage = updates.filter(u => u.stage === stage)
    expect(inStage.length).toBeGreaterThan(1)

    expect(inStage.some(u => u.status === 'running' && u.progress === 100)).toBe(false)

    const full = inStage.filter(u => u.progress === 100)
    expect(full).toHaveLength(1)
    expect(full[0]).toMatchObject({ status: 'completed', indeterminate: false })
    expect(inStage[inStage.length - 1]).toBe(full[0])

    for (let i = 1; i < inStage.length; i += 1) {
      expect(inStage[i].progress).toBeGreaterThanOrEqual(inStage[i - 1].progress)
    }
  }

  it('uv.download 末块强制回报的 100 不会把「安装 Python」段提前显示成完成', () => {
    const updates: BootstrapProgressUpdate[] = []
    const bridge = new BootstrapProgressBridge(update => updates.push(update))

    for (const percent of [0, 3.2, 41.7, 88.9, 100]) {
      bridge.observe('uv.download', '正在下载固定版本 uv', percent)
    }
    bridge.finish('运行环境准备完成')

    expectStageMonotonicAndClosedOnce(updates, 'python')
    // 段内 running 的上限是 99，末块的 100 被钳住而不是透传
    const running = updates.filter(u => u.stage === 'python' && u.status === 'running')
    expect(running.map(u => u.progress)).toEqual([10, 42, 89, 99])
    expect(running.every(u => u.indeterminate === false)).toBe(true)
  })

  it('repair 链路里 uv 下载完成后 python.* 无 percent 的事件不会把进度压回 10', () => {
    const updates: BootstrapProgressUpdate[] = []
    const bridge = new BootstrapProgressBridge(update => updates.push(update))

    bridge.observe('uv.download', '正在下载固定版本 uv', 0)
    bridge.observe('uv.download', '正在下载固定版本 uv', 50)
    bridge.observe('uv.download', '正在下载固定版本 uv', 100)
    bridge.observe('uv.verify', '固定版本 uv 已校验')
    bridge.observe('python.check', '正在检查受管 Python')
    bridge.observe('python.install', '正在准备受管 Python')
    bridge.observe('python.install', '受管 Python 已就绪')
    bridge.observe('dependencies.rebuild', '正在重建依赖环境')
    bridge.finish('运行环境准备完成')

    expectStageMonotonicAndClosedOnce(updates, 'python')
    expectStageMonotonicAndClosedOnce(updates, 'dependency')

    // 无 percent 的事件仍是 indeterminate，但数字不倒退
    const pythonAfterDownload = updates.filter(
      u => u.stage === 'python' && u.status === 'running' && u.indeterminate
    )
    expect(pythonAfterDownload.length).toBeGreaterThan(0)
    expect(pythonAfterDownload.every(u => u.progress === 99)).toBe(true)
  })

  it('镜像轮换让下载从 0 重来时段内进度不倒退', () => {
    const updates: BootstrapProgressUpdate[] = []
    const bridge = new BootstrapProgressBridge(update => updates.push(update))

    for (const percent of [0, 60, 0, 5]) {
      bridge.observe('uv.download', '正在下载固定版本 uv', percent)
    }

    const progress = updates.filter(u => u.stage === 'python').map(u => u.progress)
    expect(progress).toEqual([10, 60, 60, 60])
    for (let i = 1; i < progress.length; i += 1) {
      expect(progress[i]).toBeGreaterThanOrEqual(progress[i - 1])
    }
  })
})

// ==================== 网络细节透传（M14） ====================

describe('网络细节透传', () => {
  /** 与 execute() 里的接法一致：progress 事件把可选字段整包交给 observe。 */
  function replay(name: string, bridge: BootstrapProgressBridge): void {
    for (const event of fixtureEvents(name)) {
      if (event.type === 'progress') {
        bridge.observe(event.stage, event.message, event.percent, {
          status: event.status,
          current: event.current,
          total: event.total,
          item: event.item,
          source: event.source,
          bytesPerSecond: event.bytesPerSecond,
        })
      }
      if (event.type === 'state') bridge.observe(event.stage, event.message)
    }
  }

  function replayAll(name: string): BootstrapProgressUpdate[] {
    const updates: BootstrapProgressUpdate[] = []
    const bridge = new BootstrapProgressBridge(update => updates.push(update))
    replay(name, bridge)
    bridge.finish('运行环境准备完成')
    return updates
  }

  it('测速事件按原 stage 透传源 key 与实测速度，但不推进主进度条', () => {
    const updates = replayAll('bootstrap-network-relay.ndjson')
    const probes = updates.filter(u => u.runtimeStage === NETWORK_PROBE_STAGE)
    expect(probes).toHaveLength(18)

    const running = probes.filter(u => u.runtimeStatus === 'running')
    expect(running.map(u => u.source)).toEqual([
      'github',
      'cdn-gh-proxy',
      'edgeone-gh-proxy',
      'agentsmirror',
      'gh-proxy',
      'github',
      'cnb',
      'astral',
      'github',
      'gh-proxy',
      'pypi',
      'aliyun',
      'tsinghua',
      'ustc',
    ])
    // 正数 = 实测吞吐，0 = 探测失败，缺失 = 只测首字节（git 类源）
    expect(running.map(u => u.bytesPerSecond)).toEqual([
      5420756,
      4266111,
      16774854,
      225525,
      26201,
      undefined,
      undefined,
      8854451,
      9251466,
      0,
      7840993,
      5370009,
      0,
      164019,
    ])
    expect(running.every(u => u.item === u.source)).toBe(true)

    // 源数计数不是字节，不透传也不当百分比
    expect(
      probes.every(
        u => u.indeterminate === true && u.current === undefined && u.total === undefined
      )
    ).toBe(true)

    const done = probes.filter(u => u.runtimeStatus === 'succeeded')
    expect(done.map(u => u.message)).toEqual([
      'uv 源顺序：edgeone-gh-proxy → github → cdn-gh-proxy → agentsmirror → gh-proxy',
      'git 源顺序：github → cnb',
      'python 源顺序：github → astral → gh-proxy',
      'package-index 源顺序：pypi → aliyun → ustc → tsinghua',
    ])

    // 真机顺序：uv.check 与一条无数值的 uv.download 先到，第一轮测速挂在已开始的 python 段上
    expect(updates[0]).toMatchObject({
      stage: 'python',
      status: 'started',
      runtimeStage: 'uv.check',
    })
    expect(probes[0]).toMatchObject({ stage: 'python', status: 'running', progress: 10 })
    // 依赖段开始后的测速挂在依赖段上，进度停在段起始值
    expect(probes[probes.length - 1]).toMatchObject({
      stage: 'dependency',
      status: 'running',
      progress: 10,
    })
  })

  it('下载类 stage 透传文件名、来源、速度与字节数，百分比按字节现算', () => {
    const updates = replayAll('bootstrap-network-relay.ndjson')

    const uv = updates.filter(u => u.runtimeStage === 'uv.download')
    // 第一条是真机上测速之前那条没有数值的 running
    expect(uv[0]).toMatchObject({ indeterminate: true, progress: 10 })
    expect(uv[0].item).toBeUndefined()

    const uvBytes = uv.slice(1)
    expect(uvBytes.map(u => u.progress)).toEqual([10, 79, 99])
    expect(uvBytes.every(u => u.indeterminate === false)).toBe(true)
    expect(
      uvBytes.every(
        u => u.item === 'uv-x86_64-pc-windows-msvc.zip' && u.source === 'edgeone-gh-proxy'
      )
    ).toBe(true)
    expect(uvBytes.map(u => u.bytesPerSecond)).toEqual([0, 15036024, 19013455])
    expect(uvBytes[1]).toMatchObject({
      current: 15036024,
      total: 19013455,
      runtimeStatus: 'running',
    })

    // python.install 在仓库之后到达，挂在 repository 段上（既有段序规则），细节照常透传
    const python = updates.filter(u => u.runtimeStage === 'python.install' && u.item !== undefined)
    expect(python.map(u => u.stage)).toEqual(['repository', 'repository', 'repository'])
    expect(python.map(u => u.progress)).toEqual([10, 52, 99])
    expect(python[0].item).toBe(
      'cpython-3.12.13+20260807-x86_64-pc-windows-msvc-install_only_stripped.tar.gz'
    )
    // 中继换源后 source 跟着变
    expect(python.map(u => u.source)).toEqual(['github', 'astral', 'astral'])
  })

  it('依赖同步的 total 全程恒定、current 累计，换文件后文件名与来源跟着换', () => {
    const updates = replayAll('bootstrap-network-relay.ndjson')
    const deps = updates.filter(u => u.runtimeStage === 'dependencies.sync' && u.item !== undefined)

    expect(deps.map(u => u.item)).toEqual([
      'maafw-5.12.3-py3-none-win_amd64.whl',
      'onnxruntime-1.29.0-cp312-cp312-win_amd64.whl',
      'MaaAgentBinary-1.0.1-py3-none-any.whl',
      'onnxruntime-1.29.0-cp312-cp312-win_amd64.whl',
      'opencv_python-4.10.0.84-cp37-abi3-win_amd64.whl',
      'annotated_doc-0.0.5-py3-none-any.whl',
      'win32_setctime-1.2.0-py3-none-any.whl',
    ])
    expect(deps.map(u => u.progress)).toEqual([10, 10, 23, 45, 70, 99, 99])
    expect(deps.map(u => u.current)).toEqual([
      16384, 12295188, 33299008, 64690673, 100000000, 143019809, 143023892,
    ])
    expect(new Set(deps.map(u => u.total))).toEqual(new Set([143023892]))
    expect(deps[4].source).toBe('aliyun')

    const dependency = updates.filter(u => u.stage === 'dependency')
    expect(dependency[dependency.length - 1]).toMatchObject({ status: 'completed', progress: 100 })
  })

  it('分母中途增大时按字节算出的百分比被单调钳位停住，不倒退', () => {
    const updates: BootstrapProgressUpdate[] = []
    const bridge = new BootstrapProgressBridge(update => updates.push(update))
    const wheel = (current: number, total: number, item: string) =>
      bridge.observe('dependencies.sync', '正在下载锁定依赖', undefined, {
        status: 'running',
        current,
        total,
        item,
        source: 'aliyun',
        bytesPerSecond: 3355443,
      })

    wheel(0, 10485760, 'numpy.whl')
    wheel(8388608, 10485760, 'numpy.whl')
    // 10485760/52428800 本来是 20%，停在上一条的 80
    wheel(10485760, 52428800, 'opencv.whl')
    wheel(41943040, 52428800, 'opencv.whl')
    wheel(52428800, 52428800, 'opencv.whl')

    expect(updates.map(u => u.progress)).toEqual([10, 80, 80, 80, 99])
    expect(updates.map(u => u.total)).toEqual([10485760, 10485760, 52428800, 52428800, 52428800])
    expect(updates.map(u => u.item)).toEqual([
      'numpy.whl',
      'numpy.whl',
      'opencv.whl',
      'opencv.whl',
      'opencv.whl',
    ])
  })

  it('回放旧版 Runtime 的真实事件流时没有任何网络细节字段，段序与以前一致', () => {
    const updates = replayAll('bootstrap-success.ndjson')

    expect(updates.some(u => u.runtimeStage === NETWORK_PROBE_STAGE)).toBe(false)
    for (const update of updates) {
      expect(update.item).toBeUndefined()
      expect(update.source).toBeUndefined()
      expect(update.bytesPerSecond).toBeUndefined()
      expect(update.current).toBeUndefined()
      expect(update.total).toBeUndefined()
    }
    expect(updates.filter(u => u.status === 'started').map(u => u.stage)).toEqual([
      'python',
      'repository',
      'dependency',
    ])
  })

  it('桥接自己合成的更新（接管、收口、失败）不带 Runtime stage', () => {
    const updates: BootstrapProgressUpdate[] = []
    const bridge = new BootstrapProgressBridge(update => updates.push(update))
    bridge.takeOver()
    bridge.observe('uv.download', '正在下载固定版本 uv', 12)
    bridge.finish('运行环境准备完成')

    const synthesized = updates.filter(u => u.runtimeStage === undefined)
    expect(synthesized.map(u => u.status)).toEqual([
      'completed',
      'completed',
      'completed',
      'completed',
      'completed',
      'completed',
    ])
    expect(updates.find(u => u.runtimeStage === 'uv.download')).toMatchObject({
      stage: 'python',
      status: 'started',
      progress: 12,
    })
  })

  it('bootstrap 端到端把网络细节交到 onProgress', async () => {
    const updates: BootstrapProgressUpdate[] = []
    FakeRuntimeClient.scripts = [{ events: fixtureEvents('bootstrap-network-relay.ndjson') }]

    const outcome = await createService().bootstrap(update => updates.push(update))

    expect(outcome.success).toBe(true)
    expect(updates.filter(u => u.runtimeStage === NETWORK_PROBE_STAGE)).toHaveLength(18)
    expect(
      updates.find(
        u =>
          u.runtimeStage === 'dependencies.sync' &&
          u.item === 'opencv_python-4.10.0.84-cp37-abi3-win_amd64.whl'
      )
    ).toMatchObject({
      stage: 'dependency',
      status: 'running',
      source: 'aliyun',
      bytesPerSecond: 12000000,
      current: 100000000,
      total: 143023892,
    })
    expect(updates[updates.length - 1]).toMatchObject({ stage: 'dependency', status: 'completed' })
  })
})

describe('resolveProgressPercent', () => {
  it('有真实字节时按 current / total 现算，优先于 Runtime 给的 percent', () => {
    expect(resolveProgressPercent(5, { current: 50, total: 200 })).toBe(25)
    expect(resolveProgressPercent(undefined, { current: 50, total: 200 })).toBe(25)
  })

  it('没有分母时退回 percent', () => {
    expect(resolveProgressPercent(42, { current: 50 })).toBe(42)
    expect(resolveProgressPercent(42, { current: 50, total: 0 })).toBe(42)
    expect(resolveProgressPercent(42, {})).toBe(42)
    expect(resolveProgressPercent(undefined, {})).toBeUndefined()
  })

  it('current 越过 total 时封顶 100', () => {
    expect(resolveProgressPercent(undefined, { current: 300, total: 200 })).toBe(100)
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

// ==================== 第 0 步：Runtime 对齐 ====================

describe('第 0 步：bootstrap 之前先对齐 Runtime', () => {
  it('按目标版本、当前 exe 与 app-root 调用对齐，且在 bootstrap 命令之前', async () => {
    const order: string[] = []
    alignStub.result = { status: 'upgraded', pin: { version: 'v0.1.10' }, pinSource: 'cnb' }
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
      version: 'v5.5.0-beta.3',
      runtimePath: RUNTIME_PATH,
      appRoot: APP_ROOT,
    })
    expect(FakeRuntimeClient.calls[0].command).toEqual(['bootstrap', '--version', 'v5.5.0-beta.3'])
  })

  it('更新流程给的目标版本同样传给第 0 步', async () => {
    const service = new RuntimeInitializationService({
      launchConfig: {
        mode: 'managed',
        runtimePath: RUNTIME_PATH,
        appRoot: APP_ROOT,
        dataRoot: APP_ROOT,
      },
      mirrorService: fakeMirrorService(),
      createClient: options => new FakeRuntimeClient(options) as never,
      alignRuntimeBinary: options => alignStub.run(options),
      targetVersion: 'v5.6.0',
    })

    await service.bootstrap(() => undefined)

    expect(alignStub.calls[0].version).toBe('v5.6.0')
  })

  it('第 0 步的进度挂在「运行环境」段上，下载细节只进网络细节行、不推进百分比', async () => {
    const updates: BootstrapProgressUpdate[] = []
    alignStub.result = { status: 'upgraded', pin: { version: 'v0.1.10' } }
    const service = new RuntimeInitializationService({
      launchConfig: {
        mode: 'managed',
        runtimePath: RUNTIME_PATH,
        appRoot: APP_ROOT,
        dataRoot: APP_ROOT,
      },
      mirrorService: fakeMirrorService(),
      createClient: options => new FakeRuntimeClient(options) as never,
      alignRuntimeBinary: async options => {
        options.onProgress?.({ progress: 0, message: '正在确认 v5.5.0-beta.3 需要的 Runtime 版本' })
        options.onProgress?.({
          progress: 60,
          message: '正在从 CNB（1/5） 下载 Runtime v0.1.10',
          item: 'auto-mas-runtime-v0.1.10.exe',
          source: 'cnb',
          bytesPerSecond: 3_000_000,
          current: 12_000_000,
          total: 19_000_000,
        })
        return alignStub.run(options)
      },
    })
    FakeRuntimeClient.scripts = [
      { events: fixtureEvents('bootstrap-success.ndjson') as RuntimeEvent[] },
    ]

    await service.bootstrap(update => updates.push(update))

    const python = updates.filter(update => update.stage === 'python')
    expect(python[0]).toMatchObject({
      status: 'started',
      runtimeStage: RUNTIME_BINARY_CHECK_STAGE,
      indeterminate: true,
      message: '正在确认 v5.5.0-beta.3 需要的 Runtime 版本',
    })
    expect(python[1]).toMatchObject({
      status: 'running',
      runtimeStage: RUNTIME_BINARY_DOWNLOAD_STAGE,
      indeterminate: true,
      progress: 10,
      item: 'auto-mas-runtime-v0.1.10.exe',
      source: 'cnb',
      bytesPerSecond: 3_000_000,
      current: 12_000_000,
      total: 19_000_000,
    })
    expect(python[2]).toMatchObject({
      status: 'running',
      runtimeStage: RUNTIME_BINARY_CHECK_STAGE,
      message: 'Runtime 已更新到 v0.1.10',
    })
    // 段没有因第 0 步提前收口，随后 Runtime 自己的事件仍落在同一段并正常结束。
    expect(python.filter(update => update.status === 'completed')).toHaveLength(1)
    expect(python.at(-1)?.status).toBe('completed')
    expect(updates.map(update => update.stage)).not.toContain('complete')
  })

  it.each([
    ['unpinned', { status: 'unpinned' } as RuntimeBinaryAlignResult],
    ['current', { status: 'current', pin: { version: 'v0.1.7' } } as RuntimeBinaryAlignResult],
    ['skipped', { status: 'skipped' } as RuntimeBinaryAlignResult],
  ])('第 0 步结果为 %s 时照常 bootstrap', async (_label, result) => {
    alignStub.result = result

    const outcome = await createService().bootstrap(() => undefined)

    expect(outcome.success).toBe(true)
    expect(FakeRuntimeClient.calls).toHaveLength(1)
  })

  it('第 0 步失败时不跑 bootstrap：失败段是运行环境、可重试、给重试与打开日志', async () => {
    const updates: BootstrapProgressUpdate[] = []
    alignStub.result = {
      status: 'failed',
      code: RUNTIME_PIN_UNAVAILABLE,
      error: '无法确认 v5.5.0-beta.3 需要的 Runtime 版本：CNB 与 GitHub 都没有给出结果',
    }

    const outcome = await createService().bootstrap(update => updates.push(update))

    expect(outcome).toEqual({
      success: false,
      error: '无法确认 v5.5.0-beta.3 需要的 Runtime 版本：CNB 与 GitHub 都没有给出结果',
      code: RUNTIME_PIN_UNAVAILABLE,
      retryable: true,
      remediation: ['retry', 'open-log'],
      failedStage: 'python',
    })
    expect(FakeRuntimeClient.calls).toHaveLength(0)
    expect(updates.at(-1)).toMatchObject({
      stage: 'python',
      status: 'failed',
      message: outcome.error,
    })
  })

  it('第 0 步自己抛异常时按可重试失败处理，不让 bootstrap 裸抛', async () => {
    alignStub.throws = new Error('boom')

    const outcome = await createService().bootstrap(() => undefined)

    expect(outcome.success).toBe(false)
    expect(outcome.failedStage).toBe('python')
    expect(outcome.retryable).toBe(true)
    expect(outcome.error).toContain('boom')
    expect(FakeRuntimeClient.calls).toHaveLength(0)
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
    expect(FakeRuntimeClient.calls).toHaveLength(0)
  })

  it('上一次的取消不会带进下一次 bootstrap', async () => {
    const service = createService()
    service.cancel()

    await service.bootstrap(() => undefined)

    expect(alignStub.calls[0].isCancelled?.()).toBe(false)
  })

  it('development 模式与找不到 exe 时都不做第 0 步', async () => {
    await createService({ mode: 'development', repo: APP_ROOT }).bootstrap(() => undefined)
    expect(alignStub.calls).toHaveLength(0)

    await createService({ runtimePath: null }).bootstrap(() => undefined)
    expect(alignStub.calls).toHaveLength(0)
  })

  it('运行环境段的单步重试同样先过第 0 步，仓库段与依赖段不过', async () => {
    FakeRuntimeClient.scripts = [{ events: [helloEvent, okResult('uv.check')] }]
    await createService().retryStage('python', () => undefined)
    expect(alignStub.calls).toHaveLength(1)
    expect(FakeRuntimeClient.calls[0].command).toEqual(['environment', 'ensure'])

    alignStub.calls = []
    FakeRuntimeClient.calls = []
    FakeRuntimeClient.scripts = [{ events: [helloEvent, okResult('workspace.clone')] }]
    await createService().retryStage('repository', () => undefined)
    FakeRuntimeClient.scripts = [{ events: [helloEvent, okResult('dependencies.sync')] }]
    await createService().retryStage('dependency', () => undefined)
    expect(alignStub.calls).toHaveLength(0)
    expect(FakeRuntimeClient.calls).toHaveLength(2)
  })

  it('运行环境段重试时第 0 步失败就停在第 0 步，不跑下层命令', async () => {
    alignStub.result = {
      status: 'failed',
      code: 'RUNTIME_BINARY_DOWNLOAD_FAILED',
      error: '没能下载到本版本需要的 Runtime v0.1.10',
    }

    const outcome = await createService().retryStage('python', () => undefined)

    expect(outcome.success).toBe(false)
    expect(outcome.code).toBe('RUNTIME_BINARY_DOWNLOAD_FAILED')
    expect(outcome.failedStage).toBe('python')
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
      alignRuntimeBinary: options => alignStub.run(options),
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
