import { spawn } from 'child_process'
import { EventEmitter } from 'node:events'
import { existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { basename, dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vite-plus/test'
import { BrowserWindow } from 'electron'

import { BackendService } from './backendService'
import { InitializationService } from './initializationService'
import { getFluxdownInstallEnvironment } from './fluxdownInstallService'
import { analyticsService } from './analyticsService'
import { RUNTIME_EXE_ENV, RUNTIME_MODE_ENV } from './runtime'

vi.mock('child_process', () => ({ spawn: vi.fn() }))
vi.mock('https', () => ({
  get: () => {
    const request = new EventEmitter()
    queueMicrotask(() => request.emit('error', new Error('offline')))
    return request
  },
}))
// 同时验证开发 Electron 与打包 Electron 的环境会显式传到 Runtime，且覆盖继承值。
const appState = vi.hoisted(() => ({ isPackaged: false, appPath: '' }))
const ipcHandlers = vi.hoisted(() => new Map<string, (...args: unknown[]) => unknown>())
vi.mock('electron', () => ({
  ipcMain: {
    handle: (channel: string, handler: (...args: unknown[]) => unknown) =>
      ipcHandlers.set(channel, handler),
  },
  BrowserWindow: class {
    webContents = { isDestroyed: () => false, send: vi.fn() }
  },
  app: {
    get isPackaged() {
      return appState.isPackaged
    },
    getVersion: () => '5.5.0-beta.3',
    getAppPath: () => appState.appPath,
  },
}))
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
vi.mock('./instanceConfig', async importOriginal => ({
  ...(await importOriginal<typeof import('./instanceConfig')>()),
  resolveHttpPort: vi.fn(() => 36164),
}))

const { killAllRelatedProcesses } = await import('../utils/processManager')
const { resolveHttpPort, getRendererEnvironmentArguments } = await import('./instanceConfig')

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
// Runtime 可执行文件的存在性都用 fs 判断，借用一定存在的 node 自身路径。
const EXISTING_EXE = process.execPath

function createService(): BackendService {
  return new BackendService(appRoot)
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

/** 等第 index 次 spawn（Runtime）发生，再往那个假子进程里喂数据。 */
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
async function passEnvironmentEnsure(offset = 0): Promise<FakeChild> {
  const ensure = await waitForSpawn(offset)
  ensure.stdout.feed(fixtureLines('environment-ensure.ndjson').join(''))
  ensure.close(0)
  return waitForSpawn(offset + 1)
}

/**
 * managed 模式的 supervise 之前先跑两次 preparation（workspace check 与
 * bootstrap --if-needed，各 spawn 一次），用真实成功夹具让它们结束，
 * 再返回随后 spawn 出来的 backend supervise 子进程。
 */
async function passManagedPreparation(offset = 0): Promise<FakeChild> {
  const check = await waitForSpawn(offset)
  check.stdout.feed(fixtureLines('bootstrap-success.ndjson').join(''))
  check.close(0)
  const bootstrap = await waitForSpawn(offset + 1)
  bootstrap.stdout.feed(fixtureLines('bootstrap-success.ndjson').join(''))
  bootstrap.close(0)
  return waitForSpawn(offset + 2)
}

const fetchMock = vi.fn()

beforeEach(() => {
  appState.isPackaged = false
  appRoot = mkdtempSync(join(tmpdir(), 'auto-mas-backend-'))
  appState.appPath = join(appRoot, 'frontend')
  runtimeRoot = join(dirname(appRoot), `${basename(appRoot)}-runtime`)
  spawnMock.mockReset()
  killAllMock.mockClear()
  resolveHttpPortMock.mockClear()
  fetchMock.mockReset()
  // 各用例显式构造宿主环境，验证应用环境不会被继承值覆盖。
  delete process.env.AUTO_MAS_ENV
  // 就绪时的后端版本由健康接口给出。
  // health 默认带 version 且与前端 mock 版本（5.5.0-beta.3 归一化后）一致。
  fetchMock.mockImplementation(async (url: unknown) => {
    if (String(url).includes('/api/core/health')) {
      return { ok: true, json: async () => ({ ready: true, version: 'v5.5.0-beta.3' }) }
    }
    throw new Error('connect ECONNREFUSED')
  })
  vi.stubGlobal('fetch', fetchMock)
  delete process.env[RUNTIME_MODE_ENV]
  delete process.env[RUNTIME_EXE_ENV]
})

afterEach(() => {
  vi.unstubAllGlobals()
  process.argv = process.argv.filter(arg => arg !== '--connect-existing-backend')
  delete process.env[RUNTIME_MODE_ENV]
  delete process.env[RUNTIME_EXE_ENV]
  rmSync(appRoot, { recursive: true, force: true })
  rmSync(runtimeRoot, { recursive: true, force: true })
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
      '--shutdown-timeout',
      '30',
    ])

    // WS 根地址由 baseUrl 派生，不按 resolveHttpPort 另算。
    expect(service.getRuntimeApiEndpoints()).toEqual({
      local: 'http://127.0.0.1:36163',
      websocket: 'ws://127.0.0.1:36163',
    })
    expect(service.getStatus()).toMatchObject({ isRunning: true, pid: 4242 })
    expect(service.getStatus().runtimeSupervised).toBe(true)

    // 端口与身份归 Runtime 注入，Electron 不再注入这两个变量；开发标记则两次 spawn 都带上，
    // 让受监督的开发版后端仍按开发环境关闭遥测上报。
    expect(resolveHttpPortMock).not.toHaveBeenCalled()
    for (const index of [0, 1]) {
      expect(spawnedEnv(index).AUTO_MAS_HTTP_PORT).toBeUndefined()
      expect(spawnedEnv(index).AUTO_MAS_DEV).toBeUndefined()
      expect(spawnedEnv(index).AUTO_MAS_ENV).toBe('development')
      expect(spawnedEnv(index).AUTO_MAS_INSTALL_TOKEN).toBe(
        getFluxdownInstallEnvironment().AUTO_MAS_INSTALL_TOKEN
      )
    }

    child.stdout.feed(stoppedResultLine)
    child.close(0)
  })

  it('源码的自定义端口通过 Runtime 参数传递，端点仍采纳就绪事件', async () => {
    vi.stubEnv('AUTO_MAS_HTTP_PORT', '36184')
    resolveHttpPortMock.mockReturnValueOnce(36184)
    try {
      mockSpawn()
      const service = createService()
      const pending = service.startBackend()
      const child = await passEnvironmentEnsure()
      child.stdout.feed(helloLine + runningStateLine)
      expect(await pending).toEqual({ success: true })
      expect(spawnedArgs(1).slice(-4)).toEqual(['--port', '36184', '--shutdown-timeout', '30'])
      expect(service.getRuntimeApiEndpoints()?.local).toBe('http://127.0.0.1:36163')
      child.stdout.feed(stoppedResultLine)
      child.close(0)
    } finally {
      vi.unstubAllEnvs()
    }
  })

  it.each([1, 80, 1023])('Runtime 开发启动在准备前明确拒绝低端口 %s', async port => {
    vi.stubEnv('AUTO_MAS_HTTP_PORT', String(port))
    resolveHttpPortMock.mockReturnValueOnce(port)
    try {
      mockSpawn()
      const result = await createService().startBackend()
      expect(result).toMatchObject({ success: false, code: 'INVALID_ARGUMENT' })
      expect(result.error).toContain('1024–65535')
      expect(result.error).toContain('yarn web')
      expect(spawnMock).not.toHaveBeenCalled()
    } finally {
      vi.unstubAllEnvs()
    }
  })

  it.each([1024, 65535])('Runtime 开发端口边界 %s 正常传递', async port => {
    vi.stubEnv('AUTO_MAS_HTTP_PORT', String(port))
    resolveHttpPortMock.mockReturnValueOnce(port)
    try {
      mockSpawn()
      const service = createService()
      const pending = service.startBackend()
      const child = await passEnvironmentEnsure()
      child.stdout.feed(helloLine + runningStateLine)
      expect(await pending).toEqual({ success: true })
      expect(spawnedArgs(1)).toContain(String(port))
      child.stdout.feed(stoppedResultLine)
      child.close(0)
    } finally {
      vi.unstubAllEnvs()
    }
  })

  it.each(['completes', 'times-out'] as const)(
    '开发后端清理超过 5 秒时等待完整预算：%s',
    async outcome => {
      mockSpawn()
      const service = createService()
      const pending = service.startBackend()
      const child = await passEnvironmentEnsure()
      child.stdout.feed(helloLine + runningStateLine)
      await pending
      vi.useFakeTimers()
      try {
        const stopped = service.stopBackend()
        await vi.waitFor(() => expect(child.stdin.chunks).toHaveLength(1))
        await vi.advanceTimersByTimeAsync(7000)
        expect(child.killed).toBe(false)
        if (outcome === 'completes') {
          child.stdout.feed(stoppedResultLine)
          child.close(0)
        } else {
          await vi.advanceTimersByTimeAsync(28000)
          expect(child.killed).toBe(true)
        }
        expect(await stopped).toEqual({ success: true })
      } finally {
        vi.useRealTimers()
        if (!child.killed && child.exitCode === null) child.close(0)
      }
    }
  )

  it('Runtime 报告就绪但后端版本不匹配时显式失败，不采纳句柄', async () => {
    const service = createService()
    mockSpawn()
    // Runtime 经 ndjson 上报的 baseUrl 上跑着旧版本后端。
    fetchMock.mockImplementation(async (url: unknown) => {
      if (String(url).includes('/api/core/health')) {
        return { ok: true, json: async () => ({ ready: true, version: 'v5.6.1' }) }
      }
      throw new Error('connect ECONNREFUSED')
    })

    const pending = service.startBackend()
    const child = await passEnvironmentEnsure()
    child.stdout.feed(helloLine + runningStateLine)
    // 闸门会先向 Runtime 发 shutdown 再报错；模拟 Runtime 响应并给出终态。
    await vi.waitFor(() => expect(child.stdin.chunks).toHaveLength(1))
    expect(JSON.parse(child.stdin.chunks[0].trimEnd())).toMatchObject({ command: 'shutdown' })
    child.stdout.feed(stoppedResultLine)
    child.close(0)
    const result = await pending

    expect(result.success).toBe(false)
    expect(result.error).toContain('后端版本不匹配')
    expect(result.error).toContain('v5.6.1')
    expect(result.error).toContain('v5.5.0-beta.3')
    expect(service.getRuntimeApiEndpoints()).toBeNull()
    expect(service.getStatus().runtimeSupervised).toBe(true)
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
    // 也不再自己发 POST /api/core/close（启动闸门的健康检查除外）。
    expect(killAllMock).not.toHaveBeenCalled()
    const fetchedUrls = fetchMock.mock.calls.map(([url]) => String(url))
    expect(fetchedUrls.some(url => url.includes('/api/core/close'))).toBe(false)
    expect(child.killed).toBe(false)
    expect(service.getRuntimeApiEndpoints()).toBeNull()
    expect(service.getStatus().isRunning).toBe(false)
  })

  it.each(['before-hello', 'after-hello'] as const)(
    'environment ensure 的 %s 阶段退出会取消准备，不再启动后端',
    async phase => {
      const service = createService()
      mockSpawn()
      const pendingStart = service.startBackend()
      const ensure = await waitForSpawn(0)
      const hello = fixtureLines('environment-ensure.ndjson')[0]
      if (phase === 'after-hello') {
        ensure.stdout.feed(hello)
        await Promise.resolve()
      }
      const pendingStop = service.stopBackend()
      try {
        if (phase === 'before-hello') {
          ensure.stdout.feed(hello)
        }
        await vi.waitFor(() => expect(ensure.stdin.chunks).toHaveLength(1))
        expect(JSON.parse(ensure.stdin.chunks[0])).toMatchObject({ command: 'cancel' })
        ensure.stdout.feed(
          line({
            ...base,
            type: 'result',
            sequence: 2,
            success: false,
            code: 'OPERATION_CANCELLED',
            stage: 'uv.download',
            status: 'cancelled',
            message: '已取消',
            retryable: true,
            remediation: ['retry'],
            details: {},
          })
        )
        ensure.close(10)
        expect((await pendingStart).success).toBe(false)
        expect(await pendingStop).toEqual({ success: true })
        expect(spawnMock).toHaveBeenCalledTimes(1)
        expect(service.getStatus().isRunning).toBe(false)
        expect(killAllMock).not.toHaveBeenCalled()
      } finally {
        if (ensure.exitCode === null && !ensure.killed) ensure.close(10)
        await Promise.allSettled([pendingStart, pendingStop])
      }
    }
  )

  it.each(['before-hello', 'waiting-ready'] as const)(
    'supervise 的 %s 阶段退出会取消启动，不等待后端就绪超时',
    async phase => {
      const service = createService()
      mockSpawn()
      const pendingStart = service.startBackend()
      const child = await passEnvironmentEnsure()
      if (phase === 'waiting-ready') {
        child.stdout.feed(helloLine)
        await new Promise<void>(resolve => setImmediate(resolve))
      }
      const pendingStop = service.stopBackend()
      try {
        if (phase === 'before-hello') {
          child.stdout.feed(helloLine)
          await vi.waitFor(() => expect(child.stdin.chunks).toHaveLength(1))
          expect(JSON.parse(child.stdin.chunks[0])).toMatchObject({ command: 'shutdown' })
          expect(child.killed).toBe(false)
          child.stdout.feed(stoppedResultLine)
          child.close(0)
        } else {
          await vi.waitFor(() => expect(child.stdin.chunks).toHaveLength(1))
          expect(JSON.parse(child.stdin.chunks[0])).toMatchObject({ command: 'shutdown' })
          child.stdout.feed(stoppedResultLine)
          child.close(0)
        }
        expect((await pendingStart).success).toBe(false)
        expect(await pendingStop).toEqual({ success: true })
        expect(spawnMock).toHaveBeenCalledTimes(2)
        expect(service.getStatus().isRunning).toBe(false)
        expect(killAllMock).not.toHaveBeenCalled()
      } finally {
        if (child.exitCode === null && !child.killed) child.close(0)
        await Promise.allSettled([pendingStart, pendingStop])
      }
    }
  )

  it('版本校验期间退出通过 shutdown 等待慢清理，不直接 cancel 强杀后端', async () => {
    let finishHealth: () => void = () => undefined
    fetchMock.mockImplementationOnce(
      () =>
        new Promise(resolve => {
          finishHealth = () =>
            resolve({ ok: true, json: async () => ({ version: 'v5.5.0-beta.3' }) })
        })
    )
    const service = createService()
    mockSpawn()
    const pendingStart = service.startBackend()
    const child = await passEnvironmentEnsure()
    child.stdout.feed(helloLine + runningStateLine)
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledOnce())
    const write = child.stdin.write.bind(child.stdin)
    vi.spyOn(child.stdin, 'write').mockImplementation(chunk => {
      const result = write(chunk)
      // Runtime 的 cancel 会直接清理进程；shutdown 才请求后端收尾。
      if (JSON.parse(chunk).command === 'cancel') child.kill()
      return result
    })
    vi.useFakeTimers()
    const pendingStop = service.stopBackend()
    try {
      await vi.waitFor(() => expect(child.stdin.chunks).toHaveLength(1))
      expect(JSON.parse(child.stdin.chunks[0])).toMatchObject({ command: 'shutdown' })
      finishHealth()
      await vi.advanceTimersByTimeAsync(7000)
      expect(child.killed).toBe(false)
      child.stdout.feed(stoppedResultLine)
      child.close(0)
      expect((await pendingStart).success).toBe(false)
      expect(await pendingStop).toEqual({ success: true })
      expect(service.getStatus().isRunning).toBe(false)
    } finally {
      vi.useRealTimers()
      finishHealth()
      if (child.exitCode === null && !child.killed) child.close(0)
      await Promise.allSettled([pendingStart, pendingStop])
    }
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
  it('准备失败时合并的 stderr 保留最近 200 行', async () => {
    appState.isPackaged = true
    process.env[RUNTIME_MODE_ENV] = 'managed'
    process.env[RUNTIME_EXE_ENV] = EXISTING_EXE
    const service = createService()
    mockSpawn()

    const pending = service.startBackend()
    const child = await waitForSpawn(0)
    child.stdout.feed(
      line({
        ...base,
        type: 'hello',
        sequence: 1,
        runtimeVersion: 'dev',
        command: 'workspace check',
        capabilities: [],
      })
    )
    for (let i = 0; i < 200; i++) {
      child.stdout.feed(
        line({
          ...base,
          type: 'log',
          sequence: i + 2,
          source: 'runtime',
          stream: 'stderr',
          message: `协议-${i}`,
        })
      )
    }
    child.stderr.feed(Array.from({ length: 205 }, (_, i) => `原始-${i}`).join('\n'))
    child.close(50)

    const result = await pending
    expect(result.success).toBe(false)
    expect(result.logs?.split('\n')).toHaveLength(201)
    expect(result.logs).toContain('原始-5')
    expect(result.logs).not.toContain('原始-4\n')
  })

  it('准备失败时长日志只保留有界尾部', async () => {
    appState.isPackaged = true
    process.env[RUNTIME_MODE_ENV] = 'managed'
    process.env[RUNTIME_EXE_ENV] = EXISTING_EXE
    const service = createService()
    mockSpawn()
    const record = vi.spyOn(analyticsService, 'recordMainEvent')

    const pending = service.startBackend()
    const child = await waitForSpawn(0)
    child.stdout.feed(
      line({
        ...base,
        type: 'hello',
        sequence: 1,
        runtimeVersion: 'dev',
        command: 'workspace check',
        capabilities: [],
      })
    )
    child.stdout.feed(
      line({
        ...base,
        type: 'log',
        sequence: 2,
        source: 'runtime',
        stream: 'stdout',
        message: 'a'.repeat(100_000) + '尾部',
      })
    )
    child.stderr.feed('b'.repeat(100_000) + 'stderr尾部')
    child.close(50)

    const result = await pending
    expect(result.success).toBe(false)
    expect(result.logs?.length).toBeLessThanOrEqual(2 * 65_536 + 30)
    expect(result.logs).toContain('尾部')
    expect(result.logs).toContain('stderr尾部')
    expect(JSON.stringify(record.mock.calls)).not.toContain('stderr尾部')
    record.mockRestore()
  })

  it('准备失败时多条消息与内嵌换行均受行数和字符上限约束', async () => {
    appState.isPackaged = true
    process.env[RUNTIME_MODE_ENV] = 'managed'
    process.env[RUNTIME_EXE_ENV] = EXISTING_EXE
    const service = createService()
    mockSpawn()
    const pending = service.startBackend()
    const child = await waitForSpawn(0)
    child.stdout.feed(
      line({
        ...base,
        type: 'hello',
        sequence: 1,
        runtimeVersion: 'dev',
        command: 'workspace check',
        capabilities: [],
      })
    )
    for (let i = 0; i < 100; i++) {
      child.stdout.feed(
        line({
          ...base,
          type: 'log',
          sequence: i + 2,
          source: 'runtime',
          stream: 'stdout',
          message: 'x'.repeat(1_024),
        })
      )
    }
    child.stdout.feed(
      line({
        ...base,
        type: 'log',
        sequence: 102,
        source: 'runtime',
        stream: 'stderr',
        message: '行\n'.repeat(250) + '最后一行',
      })
    )
    child.close(50)

    const result = await pending
    const [stdout, stderr] = result.logs!.split('\n\n')
    expect(stdout.length - '[stdout]\n'.length).toBeLessThanOrEqual(65_536)
    expect(stderr.split('\n')).toHaveLength(201)
    expect(stderr).toContain('最后一行')
  })

  it('准备失败时未知日志流不标记为 stdout', async () => {
    appState.isPackaged = true
    process.env[RUNTIME_MODE_ENV] = 'managed'
    process.env[RUNTIME_EXE_ENV] = EXISTING_EXE
    const service = createService()
    mockSpawn()

    const pending = service.startBackend()
    const child = await waitForSpawn(0)
    child.stdout.feed(
      line({
        ...base,
        type: 'hello',
        sequence: 1,
        runtimeVersion: 'dev',
        command: 'workspace check',
        capabilities: [],
      })
    )
    child.stdout.feed(
      line({
        ...base,
        type: 'log',
        sequence: 2,
        source: 'runtime',
        stream: 'other',
        message: '未知流日志',
      })
    )
    child.close(50)

    const result = await pending
    expect(result.success).toBe(false)
    expect(result.logs).toBe('[other]\n未知流日志')
  })

  it.each(['workspace check', 'bootstrap'] as const)(
    '%s 准备失败时保留 Runtime 协议日志',
    async command => {
      appState.isPackaged = true
      process.env[RUNTIME_MODE_ENV] = 'managed'
      process.env[RUNTIME_EXE_ENV] = EXISTING_EXE
      const service = createService()
      mockSpawn()
      const record = vi.spyOn(analyticsService, 'recordMainEvent')

      const pending = service.startBackend()
      let preparation = await waitForSpawn(0)
      if (command === 'bootstrap') {
        preparation.stdout.feed(
          line({
            ...base,
            type: 'hello',
            sequence: 1,
            runtimeVersion: 'dev',
            command: 'workspace check',
            capabilities: [],
          }) +
            line({
              ...base,
              type: 'log',
              sequence: 2,
              source: 'runtime',
              stream: 'stdout',
              message: '上一次检查成功日志',
            }) +
            line({
              ...base,
              type: 'result',
              sequence: 3,
              success: true,
              code: 'OK',
              stage: 'workspace.check',
              status: 'succeeded',
              message: '检查完成',
              retryable: false,
              remediation: [],
              details: { healthy: true, version: 'v5.5.0-beta.3' },
            })
        )
        preparation.close(0)
        preparation = await waitForSpawn(1)
      }
      preparation.stdout.feed(
        line({
          ...base,
          type: 'hello',
          sequence: 1,
          runtimeVersion: 'dev',
          command,
          capabilities: [],
        }) +
          line({
            ...base,
            type: 'log',
            sequence: 2,
            source: 'runtime',
            stream: 'stdout',
            message: '准备步骤日志',
          }) +
          line({
            ...base,
            type: 'log',
            sequence: 3,
            source: 'runtime',
            stream: 'stderr',
            message: '依赖失败详情',
          }) +
          line({
            ...base,
            type: 'result',
            sequence: 4,
            success: false,
            code: 'DEPENDENCY_SYNC_FAILED',
            stage: 'dependency.sync',
            status: 'failed',
            message: '准备失败',
            retryable: true,
            remediation: ['retry-sync'],
            details: {},
          })
      )
      preparation.close(50)

      const result = await pending
      expect(result.success).toBe(false)
      expect(result.code).toBe('DEPENDENCY_SYNC_FAILED')
      expect(result.logs).toBe('[stdout]\n准备步骤日志\n\n[stderr]\n依赖失败详情')
      expect(record).toHaveBeenCalled()
      expect(JSON.stringify(record.mock.calls)).not.toContain('准备步骤日志')
      expect(JSON.stringify(record.mock.calls)).not.toContain('依赖失败详情')
      record.mockRestore()
      expect(spawnMock).toHaveBeenCalledTimes(command === 'bootstrap' ? 2 : 1)
    }
  )

  it('准备命令异常退出时仍保留有界日志，不把日志送入遥测', async () => {
    appState.isPackaged = true
    process.env[RUNTIME_MODE_ENV] = 'managed'
    process.env[RUNTIME_EXE_ENV] = EXISTING_EXE
    const service = createService()
    mockSpawn()
    const record = vi.spyOn(analyticsService, 'recordMainEvent')

    const pending = service.startBackend()
    const child = await waitForSpawn(0)
    child.stdout.feed(
      line({
        ...base,
        type: 'hello',
        sequence: 1,
        runtimeVersion: 'dev',
        command: 'workspace check',
        capabilities: [],
      })
    )
    for (let i = 0; i < 205; i++) {
      child.stdout.feed(
        line({
          ...base,
          type: 'log',
          sequence: i + 2,
          source: 'runtime',
          stream: 'stderr',
          message: `本地诊断-${i}`,
        })
      )
    }
    child.close(50)

    const result = await pending
    expect(result.success).toBe(false)
    expect(result.logs).toContain('本地诊断-5')
    expect(result.logs).not.toContain('本地诊断-4\n')
    expect(result.logs).toContain('本地诊断-204')
    expect(result.logs?.split('\n')).toHaveLength(201)
    expect(record).toHaveBeenCalled()
    expect(JSON.stringify(record.mock.calls)).not.toContain('本地诊断-')
    record.mockRestore()
    expect(spawnMock).toHaveBeenCalledTimes(1)
  })

  it('原 off 生产设置迁入 managed 后仍给慢清理完整的 30 秒预算', async () => {
    appState.isPackaged = true
    delete process.env[RUNTIME_MODE_ENV]
    process.env[RUNTIME_EXE_ENV] = EXISTING_EXE
    mkdirSync(join(appRoot, 'config'))
    writeFileSync(
      join(appRoot, 'config/frontend_config.json'),
      JSON.stringify({ Runtime: { LaunchMode: 'off' } })
    )
    mockSpawn()
    const service = createService()
    const pending = service.startBackend()
    const child = await passManagedPreparation()
    child.stdout.feed(helloLine + runningStateLine)
    await pending
    try {
      expect(spawnedArgs(2).slice(-6)).toEqual([
        'backend',
        'supervise',
        '--mode',
        'managed',
        '--shutdown-timeout',
        '30',
      ])
      vi.useFakeTimers()
      const stopped = service.stopBackend()
      await vi.waitFor(() => expect(child.stdin.chunks).toHaveLength(1))
      expect(JSON.parse(child.stdin.chunks[0])).toMatchObject({ command: 'shutdown' })
      await vi.advanceTimersByTimeAsync(31000)
      expect(child.killed).toBe(false)
      child.stdout.feed(stoppedResultLine)
      child.close(0)
      expect(await stopped).toEqual({ success: true })
    } finally {
      vi.useRealTimers()
      if (child.exitCode === null && !child.killed) {
        child.stdout.feed(stoppedResultLine)
        child.close(0)
      }
    }
  })

  it('不传 --repo、不先跑 environment ensure，--app-root 就是用户数据根', async () => {
    appState.isPackaged = true
    process.env.AUTO_MAS_ENV = 'development'
    process.env[RUNTIME_MODE_ENV] = 'managed'
    process.env[RUNTIME_EXE_ENV] = EXISTING_EXE
    const service = createService()
    mockSpawn()

    const pending = service.startBackend()
    // managed 的 supervise 之前先跑 workspace check 与 bootstrap 两次准备，
    // 各自 spawn 一次；第三次 spawn 才是 backend supervise。
    const child = await passManagedPreparation()
    child.stdout.feed(helloLine + runningStateLine)
    child.stdout.feed(helloLine + runningStateLine)

    expect(await pending).toEqual({ success: true })
    expect(spawnMock).toHaveBeenCalledTimes(3)
    // managed 模式 --app-root 就是用户数据根（与 dataRoot 相同），不是仓外的 runtime 目录。
    expect(spawnedArgs(2).slice(0, 2)).toEqual(['--app-root', appRoot])
    expect(spawnedArgs(2).slice(-6)).toEqual([
      'backend',
      'supervise',
      '--mode',
      'managed',
      '--shutdown-timeout',
      '30',
    ])
    expect(spawnedArgs(2)).not.toContain('--repo')
    expect(spawnedEnv(2).AUTO_MAS_ENV).toBe('production')
    expect(spawnedEnv(2).AUTO_MAS_INSTALL_TOKEN).toBe(
      getFluxdownInstallEnvironment().AUTO_MAS_INSTALL_TOKEN
    )
    expect(existsSync(runtimeRoot)).toBe(false)

    child.stdout.feed(stoppedResultLine)
    child.close(0)
  })
})

// 主进程已开始启动，renderer 晚到或重载仍须收到同一次结果，失败不自动重试。
describe('桌面前端只连接已有后端', () => {
  it.each(['development', 'managed'])('%s 不安装或接管外部后端', async mode => {
    process.argv.push('--connect-existing-backend')
    expect(getRendererEnvironmentArguments()).toContain('--auto-mas-backend-ownership=external')
    process.env[RUNTIME_MODE_ENV] = mode
    vi.resetModules()
    ipcHandlers.clear()
    const handlers = await import('../ipc/initializationHandlers')
    handlers.registerInitializationHandlers(new BrowserWindow())
    expect(
      await handlers.startDesktopStartup({ version: '5.5.0-beta.3', autoUpdate: true })
    ).toMatchObject({ success: true })

    const event = { sender: { isDestroyed: () => false, send: vi.fn() } }
    for (const channel of [
      'backend-start',
      'backend-stop',
      'backend-restart',
      'initialize',
      'install-python',
      'install-pip',
      'install-git',
      'pull-repository',
      'install-dependencies',
      'update-runtime-binary',
      'update-backend-via-runtime',
    ]) {
      const result = await Promise.resolve()
        .then(() => ipcHandlers.get(channel)?.(event))
        .catch((error: Error) => ({ success: false, error: error.message }))
      expect(result, channel).toSatisfy(
        (value: { success?: boolean; status?: string }) =>
          value.success === false || value.status === 'failed'
      )
    }
    expect(await ipcHandlers.get('check-runtime-backend-update')?.()).toMatchObject({
      staged: false,
    })
    expect(await ipcHandlers.get('check-runtime-binary-update')?.()).toMatchObject({
      status: 'skipped',
    })
    expect(await ipcHandlers.get('backend-status')?.()).toMatchObject({
      isRunning: true,
      runtimeSupervised: false,
    })
    expect(await ipcHandlers.get('get-api-endpoint')?.(event, 'local')).toBe(
      'http://127.0.0.1:36164'
    )
    fetchMock.mockRejectedValue(new Error('backend offline'))
    expect(await ipcHandlers.get('backend-status')?.()).toMatchObject({ isRunning: false })
    await handlers.stopDesktopStartup(true)
    expect(spawnMock).not.toHaveBeenCalled()
    expect(killAllMock).not.toHaveBeenCalled()
  })
})

describe('关闭时收口仍在运行的 Runtime 命令', () => {
  it.each(['no-close', 'kill-error'])(
    '监督进程 %s 时，第二次清理仍保留并处理同一进程',
    async fault => {
      process.env[RUNTIME_MODE_ENV] = 'development'
      process.env[RUNTIME_EXE_ENV] = EXISTING_EXE
      mockSpawn()
      const service = new InitializationService(appRoot)
      const startup = service.startDesktopStartup({
        version: '5.5.0-beta.3',
        initializedVersion: '5.5.0-beta.3',
        autoUpdate: false,
      })
      const child = await passEnvironmentEnsure()
      child.stdout.feed(helloLine + runningStateLine)
      expect(await startup).toMatchObject({ success: true })
      // 注入进程边界故障：结束请求已发出，但操作系统未交付 close，不能据此认定退出。
      const kill = vi.fn(() => {
        if (fault === 'kill-error') {
          child.emit('error', Object.assign(new Error('kill denied'), { code: 'EPERM' }))
          return false
        }
        child.killed = true
        return true
      })
      child.kill = kill
      vi.useFakeTimers()
      try {
        const first = service.stopDesktopStartup().then(
          () => null,
          (error: unknown) => error
        )
        await vi.advanceTimersByTimeAsync(40_000)
        expect(await first).toBeInstanceOf(Error)
        const firstAttempts = kill.mock.calls.length

        const final = service.stopDesktopStartup(true).then(
          () => null,
          (error: unknown) => error
        )
        await vi.advanceTimersByTimeAsync(40_000)
        expect(await final).toBeInstanceOf(Error)
        expect(kill.mock.calls.length).toBeGreaterThan(firstAttempts)
        expect(service.getBackendService().getStatus().isRunning).toBe(true)
        expect(spawnMock).toHaveBeenCalledTimes(2)

        child.close(null, 'SIGKILL')
        await service.stopDesktopStartup(true)
        expect(service.getBackendService().getStatus().isRunning).toBe(false)
      } finally {
        child.close(1)
        vi.useRealTimers()
      }
    }
  )

  it.each(['startup', 'repair', 'update'])(
    '%s 提交后迟到取消保留真实结果并禁止重启后端',
    async entry => {
      process.env[RUNTIME_MODE_ENV] = 'managed'
      process.env[RUNTIME_EXE_ENV] = EXISTING_EXE
      mockSpawn()
      vi.resetModules()
      ipcHandlers.clear()
      const handlers = await import('../ipc/initializationHandlers')
      handlers.registerInitializationHandlers(new BrowserWindow())
      const event = { sender: { isDestroyed: () => false, send: vi.fn() } }
      const work = Promise.resolve(
        entry === 'startup'
          ? handlers.startDesktopStartup({ version: '5.5.0-beta.3', autoUpdate: true })
          : entry === 'repair'
            ? ipcHandlers.get('install-dependencies')?.(event)
            : ipcHandlers.get('update-backend-via-runtime')?.(event, '5.5.0-beta.4')
      )
      const child = await waitForSpawn()
      const lines = fixtureLines('bootstrap-success.ndjson')
      child.stdout.feed(lines[0])
      const firstStop = handlers.stopDesktopStartup()
      const finalStop = handlers.stopDesktopStartup(true)
      await vi.waitFor(() => expect(child.stdin.chunks.join('')).toContain('cancel'))
      expect(child.killed).toBe(false)
      child.stdout.feed(lines.slice(1).join(''))
      child.close(0)
      const result = await work
      await Promise.all([firstStop, finalStop])
      expect(result).toMatchObject({ success: entry === 'repair' })
      if (entry === 'update') expect(result).toMatchObject({ phase: 'restart', cancelled: true })
      expect(child.killed).toBe(false)
      expect(spawnMock).toHaveBeenCalledTimes(1)
    }
  )

  it('无法确认进程退出时有界报错，保留关闭状态供最终清理重试', async () => {
    process.env[RUNTIME_MODE_ENV] = 'managed'
    process.env[RUNTIME_EXE_ENV] = EXISTING_EXE
    mockSpawn()
    const service = new InitializationService(appRoot)
    const work = service.startDesktopStartup({ version: '5.5.0-beta.3', autoUpdate: true })
    const child = await waitForSpawn()
    child.stdout.feed(fixtureLines('bootstrap-success.ndjson')[0])
    child.kill = () => {
      child.killed = true
      return true
    }
    vi.useFakeTimers()
    const stop = service.stopDesktopStartup(true).then(
      () => null,
      (error: unknown) => error
    )
    try {
      await vi.advanceTimersByTimeAsync(70_000)
      expect(await stop).toBeInstanceOf(Error)
      expect(() => service.resetDesktopStartup()).toThrow()
      expect(child.exitCode).toBeNull()
      expect(spawnMock).toHaveBeenCalledTimes(1)
    } finally {
      child.close(1)
      vi.useRealTimers()
      await work
    }
  })

  it.each(['startup', 'repair', 'update'])('%s 不响应取消时有界退出且不遗留命令', async entry => {
    process.env[RUNTIME_MODE_ENV] = 'managed'
    process.env[RUNTIME_EXE_ENV] = EXISTING_EXE
    mockSpawn()
    vi.resetModules()
    ipcHandlers.clear()
    const handlers = await import('../ipc/initializationHandlers')
    handlers.registerInitializationHandlers(new BrowserWindow())
    const event = { sender: { isDestroyed: () => false, send: vi.fn() } }
    const work = Promise.resolve(
      entry === 'startup'
        ? handlers.startDesktopStartup({ version: '5.5.0-beta.3', autoUpdate: true })
        : entry === 'repair'
          ? ipcHandlers.get('install-dependencies')?.(event)
          : ipcHandlers.get('update-backend-via-runtime')?.(event, '5.5.0-beta.4')
    )
    const child = await waitForSpawn()
    child.stdout.feed(fixtureLines('bootstrap-success.ndjson')[0])
    vi.useFakeTimers()
    let stopped = false
    const stop = handlers.stopDesktopStartup(true).then(() => {
      stopped = true
    })
    try {
      await vi.advanceTimersByTimeAsync(70_000)
      expect(stopped).toBe(true)
      expect(child.killed).toBe(true)
      expect(spawnMock).toHaveBeenCalledTimes(1)
    } finally {
      child.close(1)
      vi.useRealTimers()
      await Promise.allSettled([work, stop])
    }
  })
})

describe('桌面启动任务接入', () => {
  it.each(['development', 'managed'])('%s 晚到的前端保留同一启动失败', async mode => {
    process.env[RUNTIME_MODE_ENV] = mode
    process.env[RUNTIME_EXE_ENV] = join(appRoot, 'missing-runtime.exe')
    const service = new InitializationService(appRoot)
    const preferences = {
      version: '5.5.0-beta.3',
      initializedVersion: '5.5.0-beta.3',
      autoUpdate: false,
    }
    const first = service.startDesktopStartup(preferences)
    expect(await first).toMatchObject({ success: false, code: 'RUNTIME_NOT_FOUND' })
    const late = service.startDesktopStartup(preferences)
    expect(late).toBe(first)
    expect(await late).toMatchObject({ success: false, code: 'RUNTIME_NOT_FOUND' })
  })
})

describe('主进程拥有两种模式的启动生命周期', () => {
  it.each(['development', 'managed'])('%s 窗口请求在后端退出后恢复真实监督', async mode => {
    process.env[RUNTIME_MODE_ENV] = mode
    process.env[RUNTIME_EXE_ENV] = EXISTING_EXE
    mockSpawn()
    vi.resetModules()
    ipcHandlers.clear()
    const handlers = await import('../ipc/initializationHandlers')
    const window = new BrowserWindow()
    handlers.registerInitializationHandlers(window)
    const initial = handlers.startDesktopStartup({
      version: '5.5.0-beta.3',
      initializedVersion: '5.5.0-beta.3',
      autoUpdate: false,
    })
    const child =
      mode === 'development' ? await passEnvironmentEnsure() : await passManagedPreparation()
    child.stdout.feed(helloLine + runningStateLine)
    expect(await initial).toMatchObject({ success: true })
    const start = ipcHandlers.get('backend-start')
    expect(start).toBeDefined()
    expect(await start?.({ sender: window.webContents })).toMatchObject({ success: true })
    child.close(1)
    const backend = handlers.getBackendService()
    await vi.waitFor(() => expect(backend.getStatus().isRunning).toBe(false))

    const recovered = start?.({ sender: window.webContents })
    const offset = mode === 'development' ? 2 : 3
    const restarted =
      mode === 'development'
        ? await passEnvironmentEnsure(offset)
        : await passManagedPreparation(offset)
    restarted.stdout.feed(helloLine + runningStateLine)
    expect(await recovered).toMatchObject({ success: true })
    expect(backend.getStatus().isRunning).toBe(true)
    const stopped = ipcHandlers.get('backend-stop')?.()
    await vi.waitFor(() => expect(restarted.stdin.chunks.join('')).toContain('shutdown'))
    restarted.stdout.feed(stoppedResultLine)
    restarted.close(0)
    expect(await stopped).toMatchObject({ success: true })
    expect(backend.getStatus().isRunning).toBe(false)
  })

  it.each(['development', 'managed'])('%s 在窗口接入前启动并复用就绪结果', async mode => {
    process.env[RUNTIME_MODE_ENV] = mode
    process.env[RUNTIME_EXE_ENV] = EXISTING_EXE
    mockSpawn()
    const service = new InitializationService(appRoot)
    const preferences = {
      version: '5.5.0-beta.3',
      initializedVersion: '5.5.0-beta.3',
      autoUpdate: false,
    }
    const pending = service.startDesktopStartup(preferences)
    expect(service.getDesktopStartupSnapshot()).toMatchObject({
      runtimeMode: mode,
      state: 'running',
    })
    expect(() => service.resetDesktopStartup()).toThrow('启动尚未结束')
    const child =
      mode === 'development' ? await passEnvironmentEnsure() : await passManagedPreparation()
    child.stdout.feed(helloLine + runningStateLine)
    expect(await pending).toMatchObject({ success: true })
    expect(service.getBackendService().getStatus().isRunning).toBe(true)
    expect(service.getDesktopStartupSnapshot()?.state).toBe('ready')
    expect(service.startDesktopStartup(preferences)).toBe(pending)
    expect(spawnMock).toHaveBeenCalledTimes(mode === 'development' ? 2 : 3)
    child.stdout.feed(stoppedResultLine)
    child.close(0)
  })

  it.each(['development', 'managed'])('%s 准备过程中关闭不再拉起后端', async mode => {
    process.env[RUNTIME_MODE_ENV] = mode
    process.env[RUNTIME_EXE_ENV] = EXISTING_EXE
    mockSpawn()
    const service = new InitializationService(appRoot)
    const pending = service.startDesktopStartup({
      version: '5.5.0-beta.3',
      initializedVersion: '5.5.0-beta.3',
      autoUpdate: false,
    })
    const child = await waitForSpawn()
    child.stdout.feed(fixtureLines('environment-ensure.ndjson')[0])
    const stopped = service.stopDesktopStartup(true)
    await vi.waitFor(() =>
      expect(child.killed || child.stdin.chunks.join('').includes('cancel')).toBe(true)
    )
    child.stdout.feed(
      line({
        ...base,
        type: 'result',
        sequence: 9,
        success: false,
        code: 'OPERATION_CANCELLED',
        stage: 'environment.ensure',
        status: 'cancelled',
        message: 'cancelled',
        retryable: true,
        remediation: [],
      })
    )
    child.close(0)
    expect(await pending).toMatchObject({ success: false })
    await stopped
    expect(service.getBackendService().getStatus().isRunning).toBe(false)
    expect(spawnMock).toHaveBeenCalledTimes(1)
  })
})

it('managed 首次启动先完成环境准备，窗口晚到可读取各阶段结果', async () => {
  process.env[RUNTIME_MODE_ENV] = 'managed'
  process.env[RUNTIME_EXE_ENV] = EXISTING_EXE
  mockSpawn()
  vi.resetModules()
  ipcHandlers.clear()
  const handlers = await import('../ipc/initializationHandlers')
  const window = new BrowserWindow()
  handlers.registerInitializationHandlers(window)
  const pending = handlers.startDesktopStartup({ version: '5.5.0-beta.3', autoUpdate: false })
  const prepare = await waitForSpawn(0)
  expect(spawnedArgs(0)).toContain('bootstrap')
  expect(handlers.getBackendService().getStatus().isRunning).toBe(false)
  prepare.stdout.feed(fixtureLines('bootstrap-success.ndjson').join(''))
  prepare.close(0)
  for (const index of [1, 2]) {
    const child = await waitForSpawn(index)
    child.stdout.feed(fixtureLines('bootstrap-success.ndjson').join(''))
    child.close(0)
  }
  const backend = await waitForSpawn(3)
  backend.stdout.feed(helloLine + runningStateLine)
  expect(await pending).toMatchObject({ success: true })
  expect(ipcHandlers.get('desktop-startup-status')?.()).toMatchObject({
    runtimeMode: 'managed',
    fullInitialization: true,
    flowKind: 'first-run',
    state: 'ready',
  })
  expect(window.webContents.send).toHaveBeenCalledWith(
    'initialization-progress',
    expect.objectContaining({ stage: 'backend', status: 'completed' })
  )
  backend.stdout.feed(stoppedResultLine)
  backend.close(0)
})

it('环境变更进行中拒绝第二次操作，完成后允许显式恢复', async () => {
  const service = new InitializationService(appRoot)
  let finish: (value: string) => void = () => undefined
  const gate = new Promise<string>(resolve => {
    finish = resolve
  })
  const pending = service.runEnvironmentOperation(() => gate)
  try {
    await expect(service.runEnvironmentOperation(async () => 'second')).rejects.toThrow(
      '运行环境操作尚未结束'
    )
  } finally {
    finish('completed')
    await pending
  }
  expect(await service.runEnvironmentOperation(async () => 'recovered')).toBe('recovered')
})
