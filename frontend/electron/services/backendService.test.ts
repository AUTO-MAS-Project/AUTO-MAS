import { spawn } from 'child_process'
import { EventEmitter } from 'node:events'
import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { BackendService } from './backendService'
import { RUNTIME_EXE_ENV, RUNTIME_MODE_ENV, RuntimeClient } from './runtime'

vi.mock('child_process', () => ({ spawn: vi.fn() }))
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

function mockSpawn(): FakeChild {
  const child = new FakeChild()
  spawnMock.mockReturnValue(child as never)
  return child
}

// ==================== 夹具与桩 ====================

const APP_ROOT = 'D:\\AUTO-MAS'
// Runtime 与 python 可执行文件的存在性都用 fs 判断，借用一定存在的 node 自身路径。
const EXISTING_EXE = process.execPath
const LOCAL_ENDPOINT = 'http://127.0.0.1:36164'

const mirrorServiceStub = {
  getApiEndpoint: (key: string) => (key === 'local' ? LOCAL_ENDPOINT : 'ws://127.0.0.1:36164'),
  getApiEndpoints: () => ({ local: LOCAL_ENDPOINT, websocket: 'ws://127.0.0.1:36164' }),
}

function createService(): BackendService {
  return new BackendService(APP_ROOT, mirrorServiceStub as never)
}

const operationId = '01M1F6M33JFZZ7Y85BE5S849ZN'
const base = { protocol: 1, operationId, timestamp: '2026-09-01T21:20:03.442+02:00' }

function line(event: Record<string, unknown>): string {
  return `${JSON.stringify(event)}\n`
}

const helloLine = line({
  ...base,
  type: 'hello',
  sequence: 1,
  runtimeVersion: 'dev',
  command: 'backend supervise',
  capabilities: ['stdin.cancel', 'state.v1', 'log.stream'],
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

/** 等 Runtime 或 python 被 spawn 出来，再往假子进程里喂数据。 */
async function waitForSpawn(): Promise<FakeChild> {
  await vi.waitFor(() => expect(spawnMock).toHaveBeenCalled())
  return spawnMock.mock.results[0].value as FakeChild
}

function spawnedArgs(): string[] {
  return spawnMock.mock.calls[0][1] as string[]
}

function spawnedEnv(): NodeJS.ProcessEnv {
  return (spawnMock.mock.calls[0][2] as { env: NodeJS.ProcessEnv }).env
}

const fetchMock = vi.fn()

beforeEach(() => {
  spawnMock.mockReset()
  killAllMock.mockClear()
  resolveHttpPortMock.mockClear()
  fetchMock.mockReset()
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
    const child = await waitForSpawn()
    child.stdout.feed(helloLine + runningStateLine)
    const result = await pending

    expect(result).toEqual({ success: true })
    expect(spawnMock.mock.calls[0][0]).toBe(EXISTING_EXE)
    expect(spawnedArgs()).toEqual([
      '--app-root',
      APP_ROOT,
      '--output',
      'ndjson',
      '--protocol',
      '1',
      'backend',
      'supervise',
      '--mode',
      'development',
      '--repo',
      APP_ROOT,
    ])

    // WS 根地址由 baseUrl 派生，不按 resolveHttpPort 另算。
    expect(service.getRuntimeApiEndpoints()).toEqual({
      local: 'http://127.0.0.1:36163',
      websocket: 'ws://127.0.0.1:36163',
    })
    expect(service.getStatus()).toMatchObject({ isRunning: true, pid: 4242 })
    expect(service.isRuntimeSupervised()).toBe(true)

    // Runtime 原样继承宿主环境，Electron 不再注入这三个变量。
    expect(resolveHttpPortMock).not.toHaveBeenCalled()
    expect(spawnedEnv().AUTO_MAS_HTTP_PORT).toBeUndefined()
    expect(spawnedEnv().AUTO_MAS_DEV).toBeUndefined()
    expect(spawnedEnv().AUTO_MAS_ENV).toBeUndefined()

    child.stdout.feed(stoppedResultLine)
    child.close(0)
  })

  it('就绪前的失败 result 透传错误码，并把两路日志组成整块文本', async () => {
    const service = createService()
    mockSpawn()

    const pending = service.startBackend()
    const child = await waitForSpawn()

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
    const child = await waitForSpawn()
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
    const child = await waitForSpawn()
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
    const child = await waitForSpawn()
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
  it('不传 --repo，其余流程与 development 一致', async () => {
    process.env[RUNTIME_MODE_ENV] = 'managed'
    process.env[RUNTIME_EXE_ENV] = EXISTING_EXE
    const service = createService()
    mockSpawn()

    const pending = service.startBackend()
    const child = await waitForSpawn()
    child.stdout.feed(helloLine + runningStateLine)

    expect(await pending).toEqual({ success: true })
    expect(spawnedArgs().slice(-4)).toEqual(['backend', 'supervise', '--mode', 'managed'])
    expect(spawnedArgs()).not.toContain('--repo')

    child.stdout.feed(stoppedResultLine)
    child.close(0)
  })
})
