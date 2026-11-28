import { spawn } from 'child_process'
import { BrowserWindow } from 'electron'
import { EventEmitter } from 'node:events'
import { mkdtempSync, readFileSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vite-plus/test'

import { BackendService } from './backendService'
import { getFluxdownInstallEnvironment } from './fluxdownInstallService'
import { InitializationService } from './initializationService'
import { RUNTIME_EXE_ENV, RUNTIME_MODE_ENV } from './runtime'

// 更新准备本身由下载/预检集成测试守护；这里继续覆盖 Runtime 提交后的关闭协议。
vi.mock(
  './runtimeUpgradePreparation',
  () => /* 隔离真实升级准备和下载，保留后端服务生命周期测试关注的停止与重启行为。 */ ({
    prepareCoreUpgrade: async () => ({
      apply: async () => ({ status: 'skipped' }),
      dispose: async () => {},
    }),
    prepareRuntimeBinary: async () => ({
      apply: async () => ({ status: 'skipped' }),
      dispose: async () => {},
    }),
  })
)
vi.mock('child_process', () => ({ spawn: vi.fn() }))
// 更新弹窗的检查不渲染 DOM；启动、更新状态与退出协调仍运行生产代码。
vi.mock('ant-design-vue', () => ({ Modal: {}, message: {}, notification: {} }))
vi.mock('https', () => ({
  get: () => {
    const request = new EventEmitter()
    queueMicrotask(() => request.emit('error', new Error('offline')))
    return request
  },
}))
// 同时验证开发 Electron 与打包 Electron 的环境会显式传到 Runtime，且覆盖继承值。
const appState = vi.hoisted(() => ({ isPackaged: false, appPath: '', userData: '' }))
const metadataNetwork = vi.hoisted(() => ({ fetch: vi.fn(), setProxy: vi.fn() }))
const ipcHandlers = vi.hoisted(() => new Map<string, (...args: unknown[]) => unknown>())
vi.mock('electron', () => ({
  session: { fromPartition: () => metadataNetwork },
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
    getPath: (name: string) =>
      name === 'userData' ? appState.userData : join(dirname(appState.appPath), 'AUTO-MAS.exe'),
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
const { killAllRelatedProcesses } = await import('../utils/processManager')
const { getRendererEnvironmentArguments } = await import('./instanceConfig')

const spawnMock = vi.mocked(spawn)
const killAllMock = vi.mocked(killAllRelatedProcesses)

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
/** 模拟 Electron 的仓外 userData，隔离开发模式的 Runtime 根目录。 */
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
  sequence: 4,
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
async function passManagedPreparation(offset = 0, installedVersion?: string): Promise<FakeChild> {
  const check = await waitForSpawn(offset)
  check.stdout.feed(
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
        type: 'result',
        sequence: 2,
        success: true,
        code: 'OK',
        stage: 'workspace.check',
        status: 'succeeded',
        message: '检查完成',
        retryable: false,
        remediation: [],
        details: { healthy: installedVersion !== undefined, version: installedVersion },
      })
  )
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
  appState.userData = mkdtempSync(join(tmpdir(), 'auto-mas-backend-userdata-'))
  runtimeRoot = join(appState.userData, 'auto-mas-runtime')
  spawnMock.mockReset()
  killAllMock.mockClear()
  vi.stubEnv('AUTO_MAS_HTTP_PORT', undefined)
  fetchMock.mockReset()
  // 各用例显式构造宿主环境，验证应用环境不会被继承值覆盖。
  delete process.env.AUTO_MAS_ENV
  // 就绪时的后端版本由健康接口给出。
  // health 默认带 version 且与前端 mock 版本（5.5.0-beta.3 归一化后）一致。
  fetchMock.mockImplementation(async (url: unknown) => {
    if (String(url).includes('/api/core/health')) {
      return {
        ok: true,
        json: async () => ({ ready: true, businessStatus: 'ready', version: 'v5.5.0-beta.3' }),
      }
    }
    throw new Error('connect ECONNREFUSED')
  })
  vi.stubGlobal('fetch', fetchMock)
  delete process.env[RUNTIME_MODE_ENV]
  delete process.env[RUNTIME_EXE_ENV]
})

afterEach(() => {
  vi.unstubAllEnvs()
  vi.unstubAllGlobals()
  process.argv = process.argv.filter(arg => arg !== '--connect-existing-backend')
  delete process.env[RUNTIME_MODE_ENV]
  delete process.env[RUNTIME_EXE_ENV]
  rmSync(appRoot, { recursive: true, force: true })
  rmSync(appState.userData, { recursive: true, force: true })
})

describe('Runtime 启动与退出', () => {
  beforeEach(() => {
    process.env[RUNTIME_MODE_ENV] = 'development'
    process.env[RUNTIME_EXE_ENV] = EXISTING_EXE
  })

  it.each([
    [false, 'development', undefined, '36164'],
    [true, 'managed', undefined, '36163'],
    [false, 'development', '36184', '36184'],
  ] as const)(
    '应用环境决定端口，端点采纳就绪事件：%s',
    async (isPackaged, mode, port, expectedPort) => {
      appState.isPackaged = isPackaged
      process.env[RUNTIME_MODE_ENV] = mode
      vi.stubEnv('AUTO_MAS_HTTP_PORT', port)
      const service = createService()
      mockSpawn()

      const pending = service.startBackend()
      const child =
        mode === 'managed' ? await passManagedPreparation() : await passEnvironmentEnsure()
      child.stdout.feed(helloLine)
      child.stdout.feed(
        line({
          ...base,
          type: 'state',
          sequence: 2,
          stage: 'backend.health',
          status: 'running',
          details: { baseUrl: 'http://127.0.0.1:1' },
        }) +
          line({
            ...base,
            type: 'state',
            sequence: 3,
            stage: 'backend.run',
            status: 'running',
            details: {},
          })
      )
      await new Promise<void>(resolve => setImmediate(resolve))
      expect(service.getRuntimeApiEndpoints()).toBeNull()
      expect(service.getStatus().isRunning).toBe(false)
      expect(fetchMock).not.toHaveBeenCalled()
      child.stdout.feed(runningStateLine)
      const result = await pending

      expect(result).toEqual({ success: true })
      const superviseIndex = mode === 'managed' ? 2 : 1
      expect(spawnMock).toHaveBeenCalledTimes(superviseIndex + 1)
      expect(spawnedArgs(superviseIndex)).toEqual([
        '--app-root',
        mode === 'managed' ? appRoot : runtimeRoot,
        '--output',
        'ndjson',
        '--protocol',
        '1',
        'backend',
        'supervise',
        '--mode',
        mode,
        ...(mode === 'development' ? ['--repo', appRoot] : []),
        '--port',
        expectedPort,
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

      // 端口与身份由 Runtime 注入，应用环境随两次 spawn 传入，保持开发态遥测隔离。
      for (let index = 0; index <= superviseIndex; index += 1) {
        expect(spawnMock.mock.calls[index][0]).toBe(EXISTING_EXE)
        expect(spawnedEnv(index).AUTO_MAS_HTTP_PORT).toBe(port)
        expect(spawnedEnv(index).AUTO_MAS_DEV).toBeUndefined()
        expect(spawnedEnv(index).AUTO_MAS_ENV).toBe(isPackaged ? 'production' : 'development')
        expect(spawnedEnv(index).AUTO_MAS_DESKTOP_VERSION).toBe(
          isPackaged && mode === 'managed' ? '5.5.0-beta.3' : undefined
        )
        expect(spawnedEnv(index).AUTO_MAS_INSTALL_TOKEN).toBe(
          getFluxdownInstallEnvironment().AUTO_MAS_INSTALL_TOKEN
        )
      }

      child.stdout.feed(stoppedResultLine)
      child.close(0)
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

  it.each(['version', 'business'] as const)(
    '%s 检查期间后端 55 秒后才响应时，同一次启动可以完成',
    async phase => {
      vi.useFakeTimers()
      const service = createService()
      mockSpawn()
      const startup = service.startBackend()
      const child = await passEnvironmentEnsure()
      const readyAt = Date.now() + 55_000
      const health = { version: 'v5.5.0-beta.3', businessStatus: 'ready' }
      fetchMock.mockImplementation(
        (_url: string, { signal }: RequestInit) =>
          new Promise<Response>((resolve, reject) => {
            const timer = setTimeout(
              () => resolve(Response.json(health)),
              Math.max(0, readyAt - Date.now())
            )
            signal?.addEventListener(
              'abort',
              () => {
                clearTimeout(timer)
                reject(signal.reason)
              },
              { once: true }
            )
          })
      )
      try {
        if (phase === 'business') {
          fetchMock.mockResolvedValueOnce(Response.json({ ...health, businessStatus: 'running' }))
          child.stdout.feed(
            helloLine.replace('"stdin.status"', '"stdin.status","stdin.activate"') +
              runningStateLine.replace('"pid":9001', '"pid":9001,"startupActivation":"pending"')
          )
        } else {
          child.stdout.feed(helloLine + runningStateLine)
        }
        await vi.advanceTimersByTimeAsync(56_000)
        expect(child.stdin.chunks.join('')).not.toContain('"command":"shutdown"')
        if (phase === 'business') {
          expect(child.stdin.chunks.join('')).toContain('"command":"activate"')
          child.stdout.feed(
            runningStateLine
              .replace('"sequence":4', '"sequence":5')
              .replace('"pid":9001', '"pid":9001,"startupActivation":"active"')
          )
        }
        expect(await startup).toEqual({ success: true })
        expect(service.getRuntimeApiEndpoints()?.local).toBe('http://127.0.0.1:36163')
      } finally {
        child.stdout.feed(stoppedResultLine)
        child.close(0)
        await startup
        vi.useRealTimers()
      }
    }
  )

  it('就绪后持续无法读取健康检查时，在限时内结束并报告健康检查超时', async () => {
    vi.useFakeTimers()
    const service = createService()
    mockSpawn()
    fetchMock.mockRejectedValue(new TypeError('connection refused'))
    const startup = service.startBackend()
    const child = await passEnvironmentEnsure()
    try {
      child.stdout.feed(helloLine + runningStateLine)
      await vi.advanceTimersByTimeAsync(59_000)
      expect(child.stdin.chunks).toHaveLength(0)
      await vi.advanceTimersByTimeAsync(1_000)
      expect(child.stdin.chunks.join('')).toContain('"command":"shutdown"')
      child.stdout.feed(stoppedResultLine)
      child.close(0)
      expect(await startup).toMatchObject({ success: false, code: 'BACKEND_HEALTH_TIMEOUT' })
      expect(service.getRuntimeApiEndpoints()).toBeNull()
    } finally {
      if (child.exitCode === null) child.close(0)
      await startup
      vi.useRealTimers()
    }
  })

  describe.each(['before-hello', 'checking-version', 'shutdown-timeout'])('关闭阶段 %s', phase => {
    it('stopBackend 只发一次 shutdown，不做任何进程清理', async () => {
      const service = createService()
      mockSpawn()
      vi.useFakeTimers()
      let finishHealth: () => void = () => undefined
      let healthSignal: AbortSignal | null | undefined
      if (phase === 'checking-version') {
        fetchMock.mockImplementationOnce(
          (_url: string, { signal }: RequestInit) =>
            new Promise(resolve => {
              healthSignal = signal
              finishHealth = () =>
                resolve({ ok: true, json: async () => ({ version: 'v5.5.0-beta.3' }) })
            })
        )
      }

      const pendingStart = service.startBackend()
      const child = await passEnvironmentEnsure()
      if (phase !== 'before-hello') {
        child.stdout.feed(helloLine + runningStateLine)
        if (phase === 'checking-version')
          await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledOnce())
        else expect(await pendingStart).toEqual({ success: true })
      }
      const pendingStop = service.stopBackend()
      const repeatedStop = service.stopBackend()
      try {
        if (phase === 'before-hello') child.stdout.feed(helloLine)
        await vi.waitFor(() => expect(child.stdin.chunks).toHaveLength(1))
        if (phase === 'checking-version') expect(healthSignal?.aborted).toBe(true)
        const controlLine = child.stdin.chunks[0]
        expect(controlLine.endsWith('\n')).toBe(true)
        expect(JSON.parse(controlLine)).toMatchObject({
          protocol: 1,
          command: 'shutdown',
          commandId: expect.stringMatching(/^[0-7][0-9A-HJKMNP-TV-Z]{25}$/),
        })
        finishHealth()
        let stopped = false
        void pendingStop.then(() => {
          stopped = true
        })
        await vi.advanceTimersByTimeAsync(7000)
        expect(child.killed).toBe(false)
        expect(stopped).toBe(false)
        if (phase === 'shutdown-timeout') {
          await vi.advanceTimersByTimeAsync(28000)
          expect(child.killed).toBe(true)
        } else {
          child.stdout.feed(stoppedResultLine)
          await vi.advanceTimersByTimeAsync(0)
          expect(stopped).toBe(false)
          child.close(0)
        }
        expect(await Promise.all([pendingStop, repeatedStop])).toEqual([
          { success: true },
          { success: true },
        ])
        expect((await pendingStart).success).toBe(phase === 'shutdown-timeout')
      } finally {
        finishHealth()
        if (child.exitCode === null && child.signalCode === null) child.close(0)
        vi.useRealTimers()
        await Promise.allSettled([pendingStart, pendingStop, repeatedStop])
      }
      expect(child.stdin.chunks).toHaveLength(1)
      // 进程树归 Runtime 的 Job Object 管，这里不许再有 scoped taskkill，
      // 也不再自己发 POST /api/core/close（启动闸门的健康检查除外）。
      expect(killAllMock).not.toHaveBeenCalled()
      const fetchedUrls = fetchMock.mock.calls.map(([url]) => String(url))
      expect(fetchedUrls.some(url => url.includes('/api/core/close'))).toBe(false)
      expect(child.killed).toBe(phase === 'shutdown-timeout')
      expect(service.getRuntimeApiEndpoints()).toBeNull()
      expect(service.getStatus().isRunning).toBe(false)
    })
  })

  it.each([
    'before-hello',
    'after-hello',
    'supervise-before-hello',
    'supervise-waiting-ready',
    'preparation-failed',
  ] as const)('environment ensure 的 %s 阶段退出会取消准备，不再启动后端', async phase => {
    const service = createService()
    mockSpawn()
    const pendingStart = service.startBackend()
    const supervising = phase.startsWith('supervise-')
    const ensure = supervising ? await passEnvironmentEnsure() : await waitForSpawn(0)
    const hello = supervising ? helloLine : fixtureLines('environment-ensure.ndjson')[0]
    if (phase === 'preparation-failed') {
      ensure.stdout.feed(
        hello +
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
            remediation: ['retry'],
            details: {},
          })
      )
      ensure.close(50)
      expect(await pendingStart).toMatchObject({
        success: false,
        code: 'UV_DOWNLOAD_FAILED',
        retryable: true,
      })
      expect(spawnMock).toHaveBeenCalledTimes(1)
      expect(service.getRuntimeApiEndpoints()).toBeNull()
      return
    }
    if (phase === 'after-hello' || phase === 'supervise-waiting-ready') {
      ensure.stdout.feed(hello)
      await new Promise<void>(resolve => setImmediate(resolve))
    }
    const pendingStop = service.stopBackend()
    try {
      if (phase === 'before-hello' || phase === 'supervise-before-hello') {
        ensure.stdout.feed(hello)
      }
      await vi.waitFor(() => expect(ensure.stdin.chunks).toHaveLength(1))
      expect(JSON.parse(ensure.stdin.chunks[0])).toMatchObject({
        command: supervising ? 'shutdown' : 'cancel',
      })
      ensure.stdout.feed(
        supervising
          ? stoppedResultLine
          : line({
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
      ensure.close(supervising ? 0 : 10)
      expect((await pendingStart).success).toBe(false)
      expect(await pendingStop).toEqual({ success: true })
      expect(spawnMock).toHaveBeenCalledTimes(supervising ? 2 : 1)
      expect(service.getStatus().isRunning).toBe(false)
      expect(killAllMock).not.toHaveBeenCalled()
    } finally {
      if (ensure.exitCode === null && !ensure.killed) ensure.close(10)
      await Promise.allSettled([pendingStart, pendingStop])
    }
  })
})

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
  it.each(['startup', 'repair', 'update', 'recovery-wait'])(
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
      if (entry === 'recovery-wait') vi.useFakeTimers()
      const work = Promise.resolve(
        entry === 'startup' || entry === 'recovery-wait'
          ? handlers.startDesktopStartup({
              version: '5.5.0-beta.3',
              initializedVersion: entry === 'recovery-wait' ? '5.5.0-beta.3' : undefined,
              autoUpdate: entry === 'startup',
            })
          : entry === 'repair'
            ? ipcHandlers.get('install-dependencies')?.(event)
            : ipcHandlers.get('update-backend-via-runtime')?.(event, '5.5.0-beta.4')
      )
      const child = await waitForSpawn()
      if (entry === 'recovery-wait') {
        child.kill = () => {
          child.killed = true
          return true
        }
        try {
          await vi.advanceTimersByTimeAsync(10_000)
          expect(child.killed).toBe(true)
          const stopped = handlers.stopDesktopStartup(true)
          child.close(null, 'SIGKILL')
          expect(await work).toMatchObject({ success: false })
          await stopped
          await vi.advanceTimersByTimeAsync(60_000)
          expect(spawnMock).toHaveBeenCalledTimes(1)
          expect(handlers.getBackendService().getStatus().isRunning).toBe(false)
        } finally {
          child.close(null, 'SIGKILL')
          vi.useRealTimers()
          await handlers.stopDesktopStartup(true)
        }
        return
      }
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

  describe.each(['bootstrap', 'workspace', 'supervise', 'activation'])('退出确认 %s', phase => {
    it('无法确认进程退出时有界报错，保留关闭状态供最终清理重试', async () => {
      process.env[RUNTIME_MODE_ENV] = phase === 'activation' ? 'development' : 'managed'
      process.env[RUNTIME_EXE_ENV] = EXISTING_EXE
      mockSpawn()
      vi.useFakeTimers()
      const service = new InitializationService(appRoot)
      const work = service.startDesktopStartup({
        version: '5.5.0-beta.3',
        initializedVersion: phase === 'bootstrap' ? undefined : '5.5.0-beta.3',
        autoUpdate: phase === 'bootstrap',
      })
      const child =
        phase === 'supervise'
          ? await passManagedPreparation()
          : phase === 'activation'
            ? await passEnvironmentEnsure()
            : await waitForSpawn()
      child.kill = () => {
        child.killed = true
        return true
      }
      try {
        if (phase === 'bootstrap') {
          child.stdout.feed(fixtureLines('bootstrap-success.ndjson')[0])
        } else if (phase === 'activation') {
          child.stdout.feed(
            helloLine.replace('"stdin.status"', '"stdin.status","stdin.activate"') +
              line({
                ...base,
                type: 'state',
                sequence: 3,
                stage: 'backend.run',
                status: 'running',
                details: { baseUrl: 'http://127.0.0.1:36163', startupActivation: 'pending' },
              })
          )
          await vi.waitFor(() =>
            expect(child.stdin.chunks.join('')).toContain('"command":"activate"')
          )
          await vi.advanceTimersByTimeAsync(10_000)
          expect(await work).toMatchObject({ success: false, code: 'BACKEND_ACTIVATION_UNKNOWN' })
          const retry = service.getBackendService().startBackend()
          await vi.advanceTimersByTimeAsync(5_000)
          expect(await retry).toMatchObject({ success: false, code: 'BACKEND_ACTIVATION_UNKNOWN' })
        } else {
          await vi.advanceTimersByTimeAsync(12_000)
          expect(await work).toMatchObject({
            success: false,
            code: 'RUNTIME_HANDSHAKE_TIMEOUT',
            runtimeFailure: { processExited: false },
          })
          const retry = service.getBackendService().startBackend()
          await vi.advanceTimersByTimeAsync(0)
          expect(await retry).toMatchObject({
            success: false,
            code: 'RUNTIME_EXITED_UNEXPECTEDLY',
          })
        }
        const spawnCount = spawnMock.mock.calls.length
        const stop = service.stopDesktopStartup(true).then(
          () => null,
          (error: unknown) => error
        )
        await vi.advanceTimersByTimeAsync(70_000)
        expect(await stop).toBeInstanceOf(Error)
        expect(() => service.resetDesktopStartup()).toThrow()
        expect(child.exitCode).toBeNull()
        expect(spawnMock).toHaveBeenCalledTimes(spawnCount)
        child.close(null, 'SIGKILL')
        const finalStop = service.stopDesktopStartup(true)
        await vi.advanceTimersByTimeAsync(0)
        await finalStop
        await vi.advanceTimersByTimeAsync(60_000)
        expect(service.getBackendService().getStatus().isRunning).toBe(false)
        expect(spawnMock).toHaveBeenCalledTimes(spawnCount)
      } finally {
        child.close(1)
        vi.useRealTimers()
        await work
      }
    })
  })
})

describe('主进程拥有两种模式的启动生命周期', () => {
  describe.each(['handshake', 'uv-health', 'first-initialization', 'activation'])(
    '启动恢复 %s',
    fault => {
      it('持续握手超时只尝试两次，普通请求复用终态，手动重试建立新任务', async () => {
        process.env[RUNTIME_MODE_ENV] = fault === 'activation' ? 'development' : 'managed'
        process.env[RUNTIME_EXE_ENV] = EXISTING_EXE
        mockSpawn()
        vi.resetModules()
        ipcHandlers.clear()
        const handlers = await import('../ipc/initializationHandlers')
        const window = new BrowserWindow()
        handlers.registerInitializationHandlers(window)
        vi.useFakeTimers()
        const startup = handlers.startDesktopStartup({
          version: '5.5.0-beta.3',
          initializedVersion: fault === 'first-initialization' ? undefined : '5.5.0-beta.3',
          autoUpdate: false,
        })
        try {
          if (fault === 'activation') {
            const backend = await passEnvironmentEnsure()
            backend.stdout.feed(
              helloLine.replace('"stdin.status"', '"stdin.status","stdin.activate"') +
                line({
                  ...base,
                  type: 'state',
                  sequence: 3,
                  stage: 'backend.run',
                  status: 'running',
                  details: { baseUrl: 'http://127.0.0.1:36163', startupActivation: 'pending' },
                })
            )
            await vi.waitFor(() =>
              expect(backend.stdin.chunks.join('')).toContain('"command":"activate"')
            )
            await vi.advanceTimersByTimeAsync(5_000)
            expect(backend.stdin.chunks.join('')).toContain('"command":"status"')
            backend.stdout.feed(
              line({
                ...base,
                type: 'state',
                sequence: 4,
                stage: 'backend.run',
                status: 'running',
                details: { baseUrl: 'http://127.0.0.1:36163', startupActivation: 'active' },
              })
            )
            expect(await startup).toMatchObject({ success: true })
            expect(spawnMock).toHaveBeenCalledTimes(2)
            expect(ipcHandlers.get('desktop-startup-status')?.()).toMatchObject({
              attempts: [{ result: { success: true } }],
            })
            backend.stdout.feed(stoppedResultLine)
            backend.close(0)
            return
          }
          if (fault === 'uv-health' || fault === 'first-initialization') {
            const first = await waitForSpawn()
            let failed = first
            if (fault === 'uv-health') {
              first.stdout.feed(fixtureLines('bootstrap-success.ndjson').join(''))
              first.close(0)
              failed = await waitForSpawn(1)
            }
            failed.stdout.feed(
              helloLine.replace('backend supervise', 'bootstrap') +
                line({
                  ...base,
                  type: 'result',
                  sequence: 2,
                  success: false,
                  code: 'UV_EXEC_FAILED',
                  stage: 'uv.verify',
                  status: 'failed',
                  message: 'uv verification failed',
                  retryable: true,
                  remediation: ['run-doctor', 'open-log'],
                  details: { failureKind: 'process_isolation_failed' },
                })
            )
            failed.close(50)
            if (fault === 'first-initialization') {
              const second = await waitForSpawn(1)
              expect(spawnedArgs(1)).toContain('bootstrap')
              second.stdout.feed(fixtureLines('bootstrap-success.ndjson').join(''))
              second.close(0)
            }
            const backend = await passManagedPreparation(2)
            if (fault === 'first-initialization') {
              backend.stdout.feed(helloLine + runningStateLine)
              expect(await startup).toMatchObject({ success: true })
              expect(ipcHandlers.get('desktop-startup-status')?.()).toMatchObject({
                state: 'ready',
                attempts: [{ result: { code: 'UV_EXEC_FAILED' } }, { result: { success: true } }],
              })
              expect(spawnMock).toHaveBeenCalledTimes(5)
              backend.stdout.feed(stoppedResultLine)
              backend.close(0)
              return
            }
            backend.stdout.feed(
              helloLine +
                line({
                  ...base,
                  type: 'result',
                  sequence: 2,
                  success: false,
                  code: 'BACKEND_HEALTH_TIMEOUT',
                  stage: 'backend.health',
                  status: 'backend_failed',
                  message: 'health timeout',
                  retryable: true,
                  remediation: ['restart-backend', 'open-log'],
                  details: { businessDeferred: true },
                })
            )
            backend.close(60)
            expect(await startup).toMatchObject({ success: false, code: 'BACKEND_HEALTH_TIMEOUT' })
          } else {
            await waitForSpawn()
            await vi.advanceTimersByTimeAsync(10_000)
            expect(ipcHandlers.get('desktop-startup-status')?.()).toMatchObject({
              state: 'running',
            })
            expect(window.webContents.send).not.toHaveBeenCalledWith(
              'initialization-progress',
              expect.objectContaining({ status: 'failed' })
            )
            await waitForSpawn(1)
            await vi.advanceTimersByTimeAsync(10_000)
            expect(await startup).toMatchObject({
              success: false,
              code: 'RUNTIME_HANDSHAKE_TIMEOUT',
            })
          }
          expect(ipcHandlers.get('desktop-startup-status')?.()).toMatchObject({
            state: 'failed',
            attempts: [
              { attempt: 1, durationMs: expect.any(Number), result: { success: false } },
              { attempt: 2, durationMs: expect.any(Number), result: { success: false } },
            ],
          })
        } finally {
          vi.useRealTimers()
        }
        const event = { sender: window.webContents }
        for (let index = 0; index < 3; index += 1) {
          expect(await ipcHandlers.get('backend-start')?.(event)).toBe(await startup)
        }
        const offset = fault === 'uv-health' ? 5 : 2
        expect(spawnMock).toHaveBeenCalledTimes(offset)
        const manual = ipcHandlers.get('backend-start')?.(event, true)
        const child = await passManagedPreparation(offset)
        expect(ipcHandlers.get('desktop-startup-status')?.()).toMatchObject({ state: 'running' })
        child.stdout.feed(helloLine + runningStateLine)
        expect(await manual).toMatchObject({ success: true })
        expect(ipcHandlers.get('desktop-startup-status')?.()).toMatchObject({ state: 'ready' })
        expect(spawnMock).toHaveBeenCalledTimes(offset + 3)
        child.stdout.feed(stoppedResultLine)
        child.close(0)
      })
    }
  )
})

it('Runtime 故障修复沿用独立更新入口，不先调用后端材料准备', async () => {
  // 在 IPC 边界把依赖后端的准备设为离线失败，验证故障页仍进入 dev 原有更新流程。
  process.env[RUNTIME_MODE_ENV] = 'managed'
  process.env[RUNTIME_EXE_ENV] = EXISTING_EXE
  const preparation = await import('./runtimeUpgradePreparation')
  const { InitializationService } = await import('./initializationService')
  const { RuntimeInitializationService } = await import('./runtimeInitializationService')
  const prepare = vi
    .spyOn(preparation, 'prepareRuntimeBinary')
    .mockRejectedValue(new Error('backend offline'))
  vi.spyOn(InitializationService.prototype, 'runEnvironmentOperation').mockImplementation(
    async action => action()
  )
  const update = vi
    .spyOn(RuntimeInitializationService.prototype, 'updateRuntimeBinary')
    .mockResolvedValue({ status: 'current', target: { version: 'v1.2.3' } })
  const handlers = await import('../ipc/initializationHandlers')
  handlers.registerInitializationHandlers(new BrowserWindow())
  const result = await ipcHandlers.get('update-runtime-binary')?.({
    sender: { isDestroyed: () => false, send: vi.fn() },
  })
  expect(result).toMatchObject({ status: 'current' })
  expect(prepare).not.toHaveBeenCalled()
  expect(update).toHaveBeenCalledExactlyOnceWith(expect.any(Function), expect.any(Function))
})

it.each(['ready', 'failed'] as const)('插件与业务初始化 %s 后才决定是否放行', async terminal => {
  process.env[RUNTIME_MODE_ENV] = 'development'
  process.env[RUNTIME_EXE_ENV] = EXISTING_EXE
  mockSpawn()
  const service = createService()
  let businessStatus: string = 'running'
  const progress = vi.fn()
  fetchMock.mockImplementation(async () =>
    Response.json({
      version: 'v5.5.0-beta.3',
      backgroundStatus: 'ready',
      businessStatus,
      businessMessage: 'preparing plugin environment',
      backgroundError: businessStatus === 'failed' ? 'plugin installation failed' : null,
    })
  )
  const startup = service.startBackend({ onProgress: progress })
  const backend = await passEnvironmentEnsure()
  backend.stdout.feed(
    helloLine.replace('"stdin.status"', '"stdin.status","stdin.activate"') +
      line({
        ...base,
        type: 'state',
        sequence: 3,
        stage: 'backend.run',
        status: 'running',
        message: 'core ready',
        details: { baseUrl: 'http://127.0.0.1:36163', startupActivation: 'pending' },
      })
  )
  await vi.waitFor(() => expect(progress).toHaveBeenCalledWith('preparing plugin environment'))
  expect(backend.stdin.chunks.join('')).not.toContain('"command":"activate"')
  businessStatus = terminal
  if (terminal === 'ready') {
    await vi.waitFor(() => expect(backend.stdin.chunks.join('')).toContain('"command":"activate"'))
    backend.stdout.feed(
      line({
        ...base,
        type: 'state',
        sequence: 4,
        stage: 'backend.run',
        status: 'running',
        message: 'active',
        details: { baseUrl: 'http://127.0.0.1:36163', startupActivation: 'active' },
      })
    )
    expect(await startup).toMatchObject({ success: true })
  } else {
    await vi.waitFor(() => expect(backend.stdin.chunks.join('')).toContain('"command":"shutdown"'))
    backend.stdout.feed(stoppedResultLine)
    backend.close(0)
    expect(await startup).toMatchObject({
      success: false,
      error: expect.stringContaining('plugin installation failed'),
    })
    expect(backend.stdin.chunks.join('')).not.toContain('"command":"activate"')
  }
  expect(spawnMock).toHaveBeenCalledTimes(2)
  if (backend.exitCode === null) {
    backend.stdout.feed(stoppedResultLine)
    backend.close(0)
  }
})

it.each(['compatible', 'conflict', 'network'] as const)(
  '%s：只有依赖预检通过才暂存，失败保留正在运行的后端',
  async outcome => {
    process.env[RUNTIME_MODE_ENV] = 'managed'
    process.env[RUNTIME_EXE_ENV] = EXISTING_EXE
    const service = createService()
    mockSpawn()
    const startup = service.startBackend()
    const backend = await passManagedPreparation()
    backend.stdout.feed(helloLine + runningStateLine)
    expect(await startup).toEqual({ success: true })
    const commit = 'b'.repeat(40)
    let checked = false
    metadataNetwork.fetch.mockImplementation(async (url: string) => {
      // 使用候选提交的真实依赖输入，执行实际前端解析与后端预检请求。
      expect(url).toContain(`/${commit}/`)
      if (url.endsWith('/.python-version')) return new Response('3.12.13\n')
      if (url.endsWith('/uv.lock')) return new Response('version=1\n')
      return new Response('[project]\nversion="5.5.0b3"\ndependencies=["pydantic>=2"]\n')
    })
    fetchMock.mockImplementation(async (url: URL) => {
      if (url.pathname === '/api/setting/get')
        return Response.json({ code: 200, data: { Update: {} } })
      if (url.pathname === '/api/update/precheck') {
        checked = true
        if (outcome === 'network') throw new Error('precheck connection failed')
        return Response.json({
          code: 200,
          compatible: outcome === 'compatible',
          conflicts: outcome === 'conflict' ? [{ message: 'adapter requires dependency<2' }] : [],
        })
      }
      throw new Error(`Unexpected endpoint: ${url.pathname}`)
    })
    const pending = service.checkRuntimeBackendUpdate()
    const check = await waitForSpawn(3)
    const reply = (command: string, details: Record<string, unknown>, stage: string) =>
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
        type: 'result',
        sequence: 2,
        success: true,
        code: 'OK',
        stage,
        status: 'succeeded',
        message: '完成',
        retryable: false,
        remediation: [],
        details,
      })
    check.stdout.feed(
      reply(
        'workspace check',
        {
          healthy: true,
          version: 'v5.5.0-beta.3',
          commit: 'a'.repeat(40),
          remoteCommit: commit,
          updateAvailable: true,
        },
        'workspace.check'
      )
    )
    check.close(0)
    if (outcome === 'compatible') {
      const stage = await waitForSpawn(4)
      expect(checked).toBe(true)
      stage.stdout.feed(reply('workspace stage', { staged: true, commit }, 'workspace.verify'))
      stage.close(0)
      expect(await pending).toMatchObject({ staged: true, remoteCommit: commit })
    } else {
      expect(await pending).toMatchObject({
        updateAvailable: true,
        staged: false,
        remoteCommit: commit,
        precheckError:
          outcome === 'conflict' ? 'adapter requires dependency<2' : 'precheck connection failed',
      })
      expect(checked).toBe(true)
      expect(spawnMock).toHaveBeenCalledTimes(4)
    }
    expect(service.getStatus().isRunning).toBe(true)
    backend.stdout.feed(stoppedResultLine)
    backend.close(0)
  }
)
