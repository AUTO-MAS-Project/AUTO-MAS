import { spawn } from 'child_process'
import { EventEmitter } from 'node:events'
import { existsSync, mkdtempSync, readFileSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { basename, dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { BackendService } from './backendService'
import { RUNTIME_EXE_ENV, RUNTIME_MODE_ENV, RuntimeClient } from './runtime'

vi.mock('child_process', () => ({ spawn: vi.fn() }))
// resolveRuntimeLaunchMode 的构建默认值这一级要读 app.isPackaged；本文件全部用例都显式
// 设置 RUNTIME_MODE_ENV 走环境变量这一级，isPackaged 固定 false 即可，不需要逐用例切换。
vi.mock('electron', () => ({ app: { isPackaged: false } }))
vi.mock('../utils/processManager', () => ({
  killAllRelatedProcesses: vi.fn(async () => undefined),
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
// Sentry 埋点与本模块逻辑无关，直通即可。
vi.mock('./sentry', () => ({
  observeMainOperation: async (
    _name: string,
    _op: string,
    _attributes: unknown,
    operation: () => Promise<unknown>
  ) => operation(),
  recordMainCount: vi.fn(),
  recordMainDuration: vi.fn(),
}))
vi.mock('./environmentService', () => ({ isDevelopmentEnvironment: () => true }))
vi.mock('./instanceConfig', () => ({ resolveHttpPort: vi.fn(() => 36164) }))

const { killAllRelatedProcesses } = await import('../utils/processManager')
const { resolveHttpPort } = await import('./instanceConfig')

const spawnMock = vi.mocked(spawn)
const killAllMock = vi.mocked(killAllRelatedProcesses)
const resolveHttpPortMock = vi.mocked(resolveHttpPort)

const fixturesDir = join(dirname(fileURLToPath(import.meta.url)), 'runtime', '__fixtures__')

/** 夹具由本机构建的 auto-mas-runtime.exe 真实跑出来，不是手写的。 */
function fixtureLines(name: string): string[] {
  return readFileSync(join(fixturesDir, name), 'utf8')
    .split('\n')
    .filter(line => line.trim() !== '')
    .map(line => `${line}\n`)
}

// ==================== 假子进程 ====================

class FakeReadable extends EventEmitter {
  setEncoding(): this {
    return this
  }

  feed(text: string): void {
    this.emit('data', text)
  }
}

class FakeWritable extends EventEmitter {
  readonly chunks: string[] = []
  destroyed = false
  writableEnded = false

  write(chunk: string): boolean {
    this.chunks.push(chunk)
    return true
  }
}

class FakeChild extends EventEmitter {
  readonly stdout = new FakeReadable()
  readonly stderr = new FakeReadable()
  readonly stdin = new FakeWritable()
  readonly pid = 4242
  exitCode: number | null = null
  signalCode: NodeJS.Signals | null = null
  killed = false

  kill(signal?: NodeJS.Signals): boolean {
    if (this.killed || this.exitCode !== null) return true
    this.killed = true
    this.close(null, signal ?? 'SIGTERM')
    return true
  }

  close(code: number | null, signal: NodeJS.Signals | null = null): void {
    this.exitCode = code
    this.signalCode = signal
    this.emit('close', code, signal)
    this.emit('exit', code, signal)
  }
}

/** 每次 spawn 都给一个新的假子进程：development 模式一次启动会先后 spawn 两个 Runtime。 */
function mockSpawn(): void {
  spawnMock.mockImplementation(() => new FakeChild() as never)
}

// ==================== 夹具与桩 ====================

/**
 * 用户数据根（传给 BackendService 的 appRoot）。用真实临时目录而不是常量：development 模式
 * 会在 supervise 前创建仓外的 Runtime 根目录，常量路径会把目录建到真实磁盘上。
 */
let appRoot: string
/** development 模式的 Runtime 根目录：非 Electron 环境下是 appRoot 同级的 `<目录名>-runtime`。 */
let runtimeRoot: string
// Runtime 与 python 可执行文件的存在性都用 fs 判断，借用一定存在的 node 自身路径。
const EXISTING_EXE = process.execPath
const LOCAL_ENDPOINT = 'http://127.0.0.1:36164'

const mirrorServiceStub = {
  getApiEndpoint: (key: string) => (key === 'local' ? LOCAL_ENDPOINT : 'ws://127.0.0.1:36164'),
  getApiEndpoints: () => ({ local: LOCAL_ENDPOINT, websocket: 'ws://127.0.0.1:36164' }),
}

function createService(): BackendService {
  return new BackendService(appRoot, mirrorServiceStub as never)
}

const operationId = '01M1F6M33JFZZ7Y85BE5S849ZN'
const base = { protocol: 1, operationId, timestamp: '2026-09-01T21:20:03.442+02:00' }

function line(event: Record<string, unknown>): string {
  return `${JSON.stringify(event)}\n`
}

// 与 Runtime 侧 backend.go 公告的五项能力一致；没宣告 stdin.shutdown 时客户端不会发 shutdown。
const helloLine = line({
  ...base,
  type: 'hello',
  sequence: 1,
  runtimeVersion: 'dev',
  command: 'backend supervise',
  capabilities: ['stdin.cancel', 'state.v1', 'log.stream', 'stdin.shutdown', 'stdin.status'],
})

const runningStateLine = line({
  ...base,
  type: 'state',
  sequence: 3,
  stage: 'backend.run',
  status: 'running',
  message: '后端运行中',
  details: { baseUrl: 'http://127.0.0.1:36163', pid: 9001 },
})

const stoppedResultLine = line({
  ...base,
  type: 'result',
  sequence: 9,
  success: true,
  code: 'OK',
  stage: 'backend.shutdown',
  status: 'stopped',
  message: '后端已停止',
  retryable: false,
  remediation: [],
  details: {},
})

function logLine(stream: 'stdout' | 'stderr', message: string, sequence: number): string {
  return line({ ...base, type: 'log', sequence, source: 'backend', stream, message })
}

/** 等第 index 次 spawn（Runtime 或 python）发生，再往那个假子进程里喂数据。 */
async function waitForSpawn(index = 0): Promise<FakeChild> {
  await vi.waitFor(() => expect(spawnMock.mock.calls.length).toBeGreaterThan(index))
  return spawnMock.mock.results[index].value as FakeChild
}

function spawnedArgs(index = 0): string[] {
  return spawnMock.mock.calls[index][1] as string[]
}

function spawnedEnv(index = 0): NodeJS.ProcessEnv {
  return (spawnMock.mock.calls[index][2] as { env: NodeJS.ProcessEnv }).env
}

/**
 * development 模式的第一次 spawn 是 `environment ensure`：用真机夹具让它成功结束，
 * 再返回随后 spawn 出来的 `backend supervise` 子进程。
 */
async function passEnvironmentEnsure(): Promise<FakeChild> {
  const ensure = await waitForSpawn(0)
  ensure.stdout.feed(fixtureLines('environment-ensure.ndjson').join(''))
  ensure.close(0)
  return waitForSpawn(1)
}

const fetchMock = vi.fn()

beforeEach(() => {
  appRoot = mkdtempSync(join(tmpdir(), 'auto-mas-backend-'))
  runtimeRoot = join(dirname(appRoot), `${basename(appRoot)}-runtime`)
  spawnMock.mockReset()
  killAllMock.mockClear()
  resolveHttpPortMock.mockClear()
  fetchMock.mockReset()
  // 宿主环境若带着这个变量，会经 process.env 原样继承，干扰对「不设」的断言。
  delete process.env.AUTO_MAS_ENV
  // 旧链路启动前会探测是否已有后端：默认不可达。
  fetchMock.mockImplementation(async (url: unknown) => {
    if (String(url).includes('/api/core/health')) {
      return { ok: true, json: async () => ({ ready: true }) }
    }
    throw new Error('connect ECONNREFUSED')
  })
  vi.stubGlobal('fetch', fetchMock)
  delete process.env[RUNTIME_MODE_ENV]
  delete process.env[RUNTIME_EXE_ENV]
})

afterEach(() => {
  vi.unstubAllGlobals()
  delete process.env[RUNTIME_MODE_ENV]
  delete process.env[RUNTIME_EXE_ENV]
  rmSync(appRoot, { recursive: true, force: true })
  rmSync(runtimeRoot, { recursive: true, force: true })
})

// ==================== 旧链路 ====================

describe('灰度开关关闭时', () => {
  it('startBackend 仍自行 spawn python，并且不构造 Runtime 客户端', async () => {
    const service = createService()
    const superviseSpy = vi.spyOn(RuntimeClient.prototype, 'supervise')
    mockSpawn()

    const result = await service.startBackend({
      pythonPath: EXISTING_EXE,
      mainPyPath: EXISTING_EXE,
      timeout: 5000,
    })

    expect(result).toEqual({ success: true })
    expect(superviseSpy).not.toHaveBeenCalled()
    expect(spawnMock).toHaveBeenCalledOnce()
    expect(spawnMock.mock.calls[0][0]).toBe(EXISTING_EXE)
    // Runtime 链路固定带 --output ndjson，旧链路只传 main.py。
    expect(spawnedArgs()).toEqual([EXISTING_EXE])
    // 旧链路仍按 createBackendEnvironment 注入端口与开发标记。
    expect(resolveHttpPortMock).toHaveBeenCalled()
    expect(spawnedEnv().AUTO_MAS_DEV).toBe('1')
    expect(spawnedEnv().AUTO_MAS_HTTP_PORT).toBe('36164')
    expect(service.isRuntimeSupervised()).toBe(false)
    expect(service.getRuntimeApiEndpoints()).toBeNull()
  })
})

// ==================== Runtime 监督链路 ====================

describe('development 模式', () => {
  beforeEach(() => {
    process.env[RUNTIME_MODE_ENV] = 'development'
    process.env[RUNTIME_EXE_ENV] = EXISTING_EXE
  })

  it('就绪事件到达后 resolve，端点取自 Runtime 下发的 baseUrl', async () => {
    const service = createService()
    mockSpawn()

    const pending = service.startBackend()
    const child = await passEnvironmentEnsure()
    child.stdout.feed(helloLine + runningStateLine)
    const result = await pending

    expect(result).toEqual({ success: true })
    expect(spawnMock).toHaveBeenCalledTimes(2)
    expect(spawnMock.mock.calls[0][0]).toBe(EXISTING_EXE)
    expect(spawnMock.mock.calls[1][0]).toBe(EXISTING_EXE)
    // 第一步先在仓外的 Runtime 根目录种 uv：backend supervise 自己不下载 uv。
    expect(spawnedArgs(0)).toEqual([
      '--app-root',
      runtimeRoot,
      '--output',
      'ndjson',
      '--protocol',
      '1',
      'environment',
      'ensure',
    ])
    expect(existsSync(runtimeRoot)).toBe(true)
    // 第二步 supervise：--app-root 仍是仓外的 Runtime 根，--repo 才是源码根（用户数据根）。
    expect(spawnedArgs(1)).toEqual([
      '--app-root',
      runtimeRoot,
      '--output',
      'ndjson',
      '--protocol',
      '1',
      'backend',
      'supervise',
      '--mode',
      'development',
      '--repo',
      appRoot,
    ])

    // WS 根地址由 baseUrl 派生，不按 resolveHttpPort 另算。
    expect(service.getRuntimeApiEndpoints()).toEqual({
      local: 'http://127.0.0.1:36163',
      websocket: 'ws://127.0.0.1:36163',
    })
    expect(service.getStatus()).toMatchObject({ isRunning: true, pid: 4242 })
    expect(service.isRuntimeSupervised()).toBe(true)

    // 端口与身份归 Runtime 注入，Electron 不再注入这两个变量；开发标记则两次 spawn 都带上，
    // 让受监督的开发版后端仍按开发环境关闭遥测上报。
    expect(resolveHttpPortMock).not.toHaveBeenCalled()
    for (const index of [0, 1]) {
      expect(spawnedEnv(index).AUTO_MAS_HTTP_PORT).toBeUndefined()
      expect(spawnedEnv(index).AUTO_MAS_DEV).toBeUndefined()
      expect(spawnedEnv(index).AUTO_MAS_ENV).toBe('development')
    }

    child.stdout.feed(stoppedResultLine)
    child.close(0)
  })

  it('就绪前的失败 result 透传错误码，并把两路日志组成整块文本', async () => {
    const service = createService()
    mockSpawn()

    const pending = service.startBackend()
    const child = await passEnvironmentEnsure()

    // 真实夹具：--repo 指向不存在的目录，Runtime 在 backend.spawn 阶段直接失败。
    const [fixtureHello, ...fixtureRest] = fixtureLines('supervise-dev-repo-missing.ndjson')
    child.stdout.feed(fixtureHello)
    child.stdout.feed(logLine('stdout', 'AUTO-MAS backend starting', 2))
    child.stdout.feed(logLine('stderr', 'Traceback (most recent call last):', 3))
    child.stdout.feed(fixtureRest.join(''))
    child.close(2)

    const result = await pending

    expect(result.success).toBe(false)
    expect(result.code).toBe('INVALID_ARGUMENT')
    expect(result.retryable).toBe(false)
    expect(result.remediation).toEqual(['run-doctor'])
    expect(result.error).toBe('开发源码目录无效')
    expect(result.logs).toBe(
      '[stdout]\nAUTO-MAS backend starting\n\n[stderr]\nTraceback (most recent call last):'
    )
    expect(service.getRuntimeApiEndpoints()).toBeNull()
    expect(killAllMock).not.toHaveBeenCalled()
  })

  it('stopBackend 只发一次 shutdown，不做任何进程清理', async () => {
    const service = createService()
    mockSpawn()

    const pendingStart = service.startBackend()
    const child = await passEnvironmentEnsure()
    child.stdout.feed(helloLine + runningStateLine)
    await pendingStart

    const pendingStop = service.stopBackend()
    await vi.waitFor(() => expect(child.stdin.chunks).toHaveLength(1))

    const payload = JSON.parse(child.stdin.chunks[0].trimEnd())
    expect(payload).toMatchObject({ protocol: 1, command: 'shutdown' })

    child.stdout.feed(stoppedResultLine)
    child.close(0)

    expect(await pendingStop).toEqual({ success: true })
    expect(child.stdin.chunks).toHaveLength(1)
    // 进程树归 Runtime 的 Job Object 管，这里不许再有 scoped taskkill，
    // 也不再自己发 POST /api/core/close。
    expect(killAllMock).not.toHaveBeenCalled()
    expect(fetchMock).not.toHaveBeenCalled()
    expect(child.killed).toBe(false)
    expect(service.getRuntimeApiEndpoints()).toBeNull()
    expect(service.getStatus().isRunning).toBe(false)
  })

  it('Runtime 未给终态就退出时归为 RUNTIME_EXITED_UNEXPECTEDLY，诊断输出并入 stderr 块', async () => {
    const service = createService()
    mockSpawn()

    const pending = service.startBackend()
    const child = await passEnvironmentEnsure()
    child.stdout.feed(helloLine)
    child.stdout.feed(logLine('stdout', 'AUTO-MAS backend starting', 2))
    child.stderr.feed('auto-mas-runtime: 后端进程树清理失败\n')
    child.close(60)

    const result = await pending

    expect(result.success).toBe(false)
    expect(result.code).toBe('RUNTIME_EXITED_UNEXPECTEDLY')
    expect(result.retryable).toBe(true)
    expect(result.logs).toBe(
      '[stdout]\nAUTO-MAS backend starting\n\n[stderr]\nauto-mas-runtime: 后端进程树清理失败'
    )
    expect(killAllMock).not.toHaveBeenCalled()
  })

  it('迟迟不就绪时请求关闭 Runtime，并以它给出的终态报告失败', async () => {
    const service = createService()
    mockSpawn()

    const pending = service.startBackend({ timeout: 20 })
    const child = await passEnvironmentEnsure()
    child.stdout.feed(helloLine)

    // 超时后本模块只发 shutdown，不 kill；这里模拟 Runtime 响应关闭并给出终态。
    await vi.waitFor(() => expect(child.stdin.chunks).toHaveLength(1))
    expect(JSON.parse(child.stdin.chunks[0].trimEnd())).toMatchObject({ command: 'shutdown' })
    child.stdout.feed(
      line({
        ...base,
        type: 'result',
        sequence: 4,
        success: false,
        code: 'BACKEND_HEALTH_TIMEOUT',
        stage: 'backend.health',
        status: 'backend_failed',
        message: '后端健康检查超时',
        retryable: true,
        remediation: ['restart-backend', 'open-log'],
        details: {},
      })
    )
    child.close(60)

    const result = await pending

    expect(result.success).toBe(false)
    expect(result.code).toBe('BACKEND_HEALTH_TIMEOUT')
    expect(result.remediation).toEqual(['restart-backend', 'open-log'])
    expect(child.killed).toBe(false)
    expect(killAllMock).not.toHaveBeenCalled()
  })

  it('environment ensure 失败时不再 supervise，按它的结果码报告失败', async () => {
    const service = createService()
    mockSpawn()

    const pending = service.startBackend()
    const ensure = await waitForSpawn(0)
    ensure.stdout.feed(
      line({
        ...base,
        type: 'hello',
        sequence: 1,
        runtimeVersion: 'dev',
        command: 'environment ensure',
        capabilities: ['stdin.cancel', 'state.v1'],
      })
    )
    ensure.stderr.feed('auto-mas-runtime: 下载 uv 失败\n')
    ensure.stdout.feed(
      line({
        ...base,
        type: 'result',
        sequence: 2,
        success: false,
        code: 'UV_DOWNLOAD_FAILED',
        stage: 'uv.download',
        status: 'failed',
        message: '下载 uv 失败',
        retryable: true,
        remediation: ['retry', 'switch-mirror'],
        details: {},
      })
    )
    ensure.close(50)

    const result = await pending

    expect(result.success).toBe(false)
    expect(result.code).toBe('UV_DOWNLOAD_FAILED')
    expect(result.retryable).toBe(true)
    expect(result.remediation).toEqual(['retry', 'switch-mirror'])
    expect(result.error).toBe('下载 uv 失败')
    expect(result.logs).toBe('[stderr]\nauto-mas-runtime: 下载 uv 失败')
    // uv 没就绪就不该起 supervise，也不该有任何旧链路清理。
    expect(spawnMock).toHaveBeenCalledTimes(1)
    expect(service.getRuntimeApiEndpoints()).toBeNull()
    expect(killAllMock).not.toHaveBeenCalled()
  })

  it('就绪只认 backend.run running 且带 baseUrl，其他阶段的 running 不算', async () => {
    const service = createService()
    mockSpawn()

    const pending = service.startBackend()
    const child = await passEnvironmentEnsure()
    child.stdout.feed(helloLine)
    // 同名 status 但阶段不对，或阶段对了却没有 baseUrl，都不能让启动成功。
    child.stdout.feed(
      line({
        ...base,
        type: 'state',
        sequence: 2,
        stage: 'backend.health',
        status: 'running',
        message: '健康检查中',
        details: { baseUrl: 'http://127.0.0.1:1' },
      })
    )
    child.stdout.feed(
      line({
        ...base,
        type: 'state',
        sequence: 3,
        stage: 'backend.run',
        status: 'running',
        message: '后端运行中',
        details: { pid: 9001 },
      })
    )
    await new Promise(resolve => setTimeout(resolve, 20))
    expect(service.getRuntimeApiEndpoints()).toBeNull()
    expect(service.getStatus().isRunning).toBe(false)

    child.stdout.feed(runningStateLine)
    expect(await pending).toEqual({ success: true })
    expect(service.getRuntimeApiEndpoints()?.local).toBe('http://127.0.0.1:36163')

    child.stdout.feed(stoppedResultLine)
    child.close(0)
  })

  it('启动阶段每路日志只保留最近 200 行', async () => {
    const service = createService()
    mockSpawn()

    const pending = service.startBackend()
    const child = await passEnvironmentEnsure()
    child.stdout.feed(helloLine)
    for (let i = 1; i <= 250; i += 1) {
      child.stdout.feed(logLine('stdout', `out ${i}`, 1 + i))
    }
    for (let i = 1; i <= 3; i += 1) {
      child.stdout.feed(logLine('stderr', `err ${i}`, 300 + i))
    }
    child.close(60)

    const result = await pending

    expect(result.success).toBe(false)
    const [stdoutBlock, stderrBlock] = (result.logs ?? '').split('\n\n')
    const stdoutLines = stdoutBlock.split('\n').slice(1)
    expect(stdoutLines).toHaveLength(200)
    expect(stdoutLines[0]).toBe('out 51')
    expect(stdoutLines.at(-1)).toBe('out 250')
    expect(stderrBlock).toBe('[stderr]\nerr 1\nerr 2\nerr 3')
  })

  it('关闭时 Runtime 没给终态就退出，进程已不在则按已停止处理', async () => {
    const service = createService()
    mockSpawn()

    const pendingStart = service.startBackend()
    const child = await passEnvironmentEnsure()
    child.stdout.feed(helloLine + runningStateLine)
    await pendingStart

    const pendingStop = service.stopBackend()
    await vi.waitFor(() => expect(child.stdin.chunks).toHaveLength(1))
    // Runtime 收到 shutdown 后直接退出、没有 result：进程树已随 Job Object 回收。
    child.close(60)

    expect(await pendingStop).toEqual({ success: true })
    expect(service.getStatus().isRunning).toBe(false)
    expect(killAllMock).not.toHaveBeenCalled()
  })

  it('关闭超时被客户端 kill 后同样算作已停止，不再报「无法安全退出」', async () => {
    vi.useFakeTimers()
    try {
      const service = createService()
      mockSpawn()

      const pendingStart = service.startBackend()
      const child = await passEnvironmentEnsure()
      child.stdout.feed(helloLine + runningStateLine)
      await pendingStart

      const pendingStop = service.stopBackend()
      await vi.waitFor(() => expect(child.stdin.chunks).toHaveLength(1))
      expect(child.killed).toBe(false)

      // Runtime 对 shutdown 毫无反应：30 秒后客户端 kill，假子进程随之 close。
      await vi.advanceTimersByTimeAsync(30_000)

      expect(child.killed).toBe(true)
      expect(await pendingStop).toEqual({ success: true })
      expect(service.getStatus().isRunning).toBe(false)
    } finally {
      vi.useRealTimers()
    }
  })

  it('hello 未宣告 stdin.shutdown 时 stopBackend 不发命令，直接 kill 并算作已停止', async () => {
    const service = createService()
    mockSpawn()

    const pendingStart = service.startBackend()
    const child = await passEnvironmentEnsure()
    child.stdout.feed(
      line({
        ...base,
        type: 'hello',
        sequence: 1,
        runtimeVersion: 'dev',
        command: 'backend supervise',
        capabilities: ['stdin.cancel', 'state.v1', 'log.stream'],
      }) + runningStateLine
    )
    await pendingStart

    expect(await service.stopBackend()).toEqual({ success: true })
    expect(child.stdin.chunks).toEqual([])
    expect(child.killed).toBe(true)
    expect(service.getStatus().isRunning).toBe(false)
  })

  it('找不到 Runtime 可执行文件时按 RUNTIME_NOT_FOUND 失败，不回退旧链路', async () => {
    delete process.env[RUNTIME_EXE_ENV]
    const service = createService()

    const result = await service.startBackend({
      pythonPath: EXISTING_EXE,
      mainPyPath: EXISTING_EXE,
    })

    expect(result.success).toBe(false)
    expect(result.code).toBe('RUNTIME_NOT_FOUND')
    expect(result.retryable).toBe(false)
    expect(result.remediation).toEqual(['update-desktop', 'contact-support'])
    // 一次生命周期只走一条链路：既没有 spawn python，也没有 spawn Runtime。
    expect(spawnMock).not.toHaveBeenCalled()
    expect(killAllMock).not.toHaveBeenCalled()
  })
})

describe('managed 模式', () => {
  it('不传 --repo、不先跑 environment ensure，--app-root 就是用户数据根', async () => {
    process.env[RUNTIME_MODE_ENV] = 'managed'
    process.env[RUNTIME_EXE_ENV] = EXISTING_EXE
    const service = createService()
    mockSpawn()

    const pending = service.startBackend()
    // managed 的 bootstrap 已包含 uv 准备，第一次 spawn 直接就是 supervise。
    const child = await waitForSpawn()
    child.stdout.feed(helloLine + runningStateLine)

    expect(await pending).toEqual({ success: true })
    expect(spawnMock).toHaveBeenCalledTimes(1)
    expect(spawnedArgs().slice(0, 2)).toEqual(['--app-root', appRoot])
    expect(spawnedArgs().slice(-4)).toEqual(['backend', 'supervise', '--mode', 'managed'])
    expect(spawnedArgs()).not.toContain('--repo')
    expect(spawnedEnv().AUTO_MAS_ENV).toBeUndefined()
    expect(existsSync(runtimeRoot)).toBe(false)

    child.stdout.feed(stoppedResultLine)
    child.close(0)
  })
})
