import { spawn } from 'child_process'
import { EventEmitter } from 'node:events'
import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vite-plus/test'

import { RuntimeClient, buildRuntimeArgs, readRuntimeBaseUrl } from './client'
import { RuntimeClientError } from './protocol'

vi.mock('child_process', () => ({ spawn: vi.fn() }))
// logger 会拉起 electron-log，与本模块逻辑无关，直接替换掉；共用一个实例以便断言日志调用。
const loggerMock = vi.hoisted(() => ({
  error: vi.fn(),
  warn: vi.fn(),
  info: vi.fn(),
  verbose: vi.fn(),
  debug: vi.fn(),
  silly: vi.fn(),
}))
vi.mock('../logger', () => ({
  getLogger: () => loggerMock,
}))

const fixturesDir = join(dirname(fileURLToPath(import.meta.url)), '__fixtures__')

/** 夹具由本机构建的 auto-mas-runtime.exe 真实跑出来，不是手写的。 */
function fixture(name: string): string {
  return readFileSync(join(fixturesDir, name), 'utf8')
}

// ==================== 假子进程 ====================

/** 同步投递数据的假可读流，避免测试里跟 PassThrough 的异步节奏纠缠。 */
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
  }
}

const spawnMock = vi.mocked(spawn)

function mockSpawn(): FakeChild {
  const child = new FakeChild()
  spawnMock.mockReturnValue(child as never)
  return child
}

// Runtime 可执行文件的存在性用 fs.existsSync 判断，这里借用一定存在的 node 自身路径。
const RUNTIME_PATH = process.execPath
const APP_ROOT = 'D:\\AUTO-MAS'

function createClient(overrides: Record<string, unknown> = {}) {
  return new RuntimeClient({ runtimePath: RUNTIME_PATH, appRoot: APP_ROOT, ...overrides })
}

function line(event: Record<string, unknown>): string {
  return `${JSON.stringify(event)}\n`
}

beforeEach(() => {
  spawnMock.mockReset()
  for (const fn of Object.values(loggerMock)) fn.mockClear()
})

afterEach(() => {
  vi.useRealTimers()
})

// ==================== 参数与工具 ====================

describe('buildRuntimeArgs', () => {
  it('机器调用固定带上 ndjson 与协议 1，全局选项在子命令之前', () => {
    const args = buildRuntimeArgs(
      {
        runtimePath: RUNTIME_PATH,
        appRoot: APP_ROOT,
        mirrors: [
          { kind: 'git', key: 'ghproxy' },
          { kind: 'uv', key: 'tuna' },
        ],
        mirrorOnly: true,
        offline: false,
      },
      ['bootstrap', '--version', 'v5.5.0-beta.3']
    )

    expect(args).toEqual([
      '--app-root',
      APP_ROOT,
      '--output',
      'ndjson',
      '--protocol',
      '1',
      '--mirror',
      'git=ghproxy',
      '--mirror',
      'uv=tuna',
      '--mirror-only',
      'bootstrap',
      '--version',
      'v5.5.0-beta.3',
    ])
  })
})

// ==================== run ====================

describe('RuntimeClient.run', () => {
  it('跑通真实 version 输出并返回终态 result', async () => {
    const client = createClient({ env: { AUTO_MAS_TELEMETRY: 'disabled' } })
    const child = mockSpawn()
    const progress: string[] = []

    const pending = client.run(['version'], {
      onProgress: event => progress.push(`${event.stage}:${event.status}`),
    })
    child.stdout.feed(fixture('version.ndjson'))
    child.close(0)
    const outcome = await pending

    expect(outcome.success).toBe(true)
    expect(outcome.code).toBe('OK')
    expect(outcome.hello.command).toBe('version')
    expect(outcome.hello.capabilities).toEqual([])
    expect(outcome.result.details.runtimeVersion).toBe('dev')
    expect(outcome.exitCode).toBe(0)
    expect(progress).toEqual(['runtime.handshake:succeeded'])

    // 必须用参数数组启动，不能拼 shell 字符串。
    expect(spawnMock).toHaveBeenCalledTimes(1)
    const [command, args, options] = spawnMock.mock.calls[0]
    expect(command).toBe(RUNTIME_PATH)
    expect(args).toEqual([
      '--app-root',
      APP_ROOT,
      '--output',
      'ndjson',
      '--protocol',
      '1',
      'version',
    ])
    expect(options).toMatchObject({ windowsHide: true })
    expect((options as { env: NodeJS.ProcessEnv }).env.AUTO_MAS_TELEMETRY).toBe('disabled')
    expect((options as { shell?: unknown }).shell).toBeUndefined()
  })

  it('握手前的坏 JSON 行让本次调用失败，并带上原始行', async () => {
    const client = createClient()
    const child = mockSpawn()
    const protocolErrors: RuntimeClientError[] = []

    const pending = client.run(['version'], {
      onProtocolError: error => protocolErrors.push(error),
    })
    child.stdout.feed('{"protocol":1,\n')

    await expect(pending).rejects.toMatchObject({
      code: 'RUNTIME_PROTOCOL_ERROR',
      retryable: false,
      details: { line: '{"protocol":1,' },
    })
    expect(protocolErrors).toHaveLength(1)
    expect(child.killed).toBe(true)
  })

  it('握手后的坏行只记录并回调，不 kill 在途命令', async () => {
    const client = createClient()
    const child = mockSpawn()
    const protocolErrors: RuntimeClientError[] = []

    const pending = client.run(['version'], {
      onProtocolError: error => protocolErrors.push(error),
    })
    const [helloLine, progressLine, resultLine] = fixture('version.ndjson').trim().split('\n')
    child.stdout.feed(`${helloLine}\n{"protocol":1,\n${progressLine}\n`)

    expect(protocolErrors).toHaveLength(1)
    expect(protocolErrors[0].code).toBe('RUNTIME_PROTOCOL_ERROR')
    expect(child.killed).toBe(false)

    child.stdout.feed(`${resultLine}\n`)
    child.close(0)
    const outcome = await pending

    expect(outcome.success).toBe(true)
    expect(outcome.protocolErrors).toHaveLength(1)
    expect(outcome.events.map(event => event.type)).toEqual(['hello', 'progress', 'result'])
  })

  it('hello 迟迟不来时报 RUNTIME_HANDSHAKE_TIMEOUT', async () => {
    const client = createClient()
    const child = mockSpawn()

    const pending = client.run(['version'], { handshakeTimeoutMs: 20 })
    child.stderr.feed('auto-mas-runtime: 卡住了\n')

    await expect(pending).rejects.toMatchObject({
      code: 'RUNTIME_HANDSHAKE_TIMEOUT',
      retryable: true,
    })
    expect(child.killed).toBe(true)
  })

  it('hello.protocol 不是 1 时报 RUNTIME_PROTOCOL_MISMATCH', async () => {
    const client = createClient()
    const child = mockSpawn()

    const pending = client.run(['version'])
    child.stdout.feed(
      line({
        protocol: 2,
        type: 'hello',
        operationId: '01M1F6K7P71J6TMW6J45CJNS63',
        sequence: 1,
        timestamp: '2026-09-01T21:19:35.367+02:00',
        runtimeVersion: 'dev',
        command: 'version',
        capabilities: [],
      })
    )

    await expect(pending).rejects.toMatchObject({
      code: 'RUNTIME_PROTOCOL_MISMATCH',
      retryable: false,
      details: { actualProtocol: 2, expectedProtocol: 1 },
    })
  })

  it('进程在 result 之前退出时报 RUNTIME_EXITED_UNEXPECTEDLY 并带退出码与 stderr', async () => {
    const client = createClient()
    const child = mockSpawn()
    const [helloLine] = fixture('version.ndjson').trim().split('\n')

    const pending = client.run(['doctor'])
    child.stdout.feed(`${helloLine}\n`)
    child.stderr.feed('panic: 崩了\n')
    child.close(50)

    await expect(pending).rejects.toMatchObject({
      code: 'RUNTIME_EXITED_UNEXPECTEDLY',
      retryable: true,
      details: { exitCode: 50, stderr: 'panic: 崩了\n' },
    })
  })
})

// ==================== supervise ====================

describe('RuntimeClient.supervise', () => {
  const operationId = '01M1F6M33JFZZ7Y85BE5S849ZN'
  const base = { protocol: 1, operationId, timestamp: '2026-09-01T21:20:03.442+02:00' }

  // 与 Runtime 侧 backend.go 公告的五项能力一致；早期构建只公告前三项（见 ndjson 夹具）。
  const capabilities = ['stdin.cancel', 'state.v1', 'log.stream', 'stdin.shutdown', 'stdin.status']

  const helloLine = line({
    ...base,
    type: 'hello',
    sequence: 1,
    runtimeVersion: 'dev',
    command: 'backend supervise',
    capabilities,
  })

  const runningStateLine = line({
    ...base,
    type: 'state',
    sequence: 2,
    stage: 'backend.run',
    status: 'running',
    message: '后端运行中',
    details: { baseUrl: 'http://127.0.0.1:36163', pid: 9001 },
  })

  const stoppedResultLine = line({
    ...base,
    type: 'result',
    sequence: 3,
    success: true,
    code: 'OK',
    stage: 'backend.shutdown',
    status: 'stopped',
    message: '后端已停止',
    retryable: false,
    remediation: [],
    details: {},
  })

  it('握手后返回句柄，state 事件带出 baseUrl', async () => {
    const client = createClient()
    const child = mockSpawn()
    const states: string[] = []

    const pendingHandle = client.supervise({
      mode: 'managed',
      onState: event => states.push(`${event.status}:${readRuntimeBaseUrl(event.details)}`),
    })
    child.stdout.feed(helloLine)
    const handle = await pendingHandle
    child.stdout.feed(runningStateLine)

    expect(handle.hello.command).toBe('backend supervise')
    expect(handle.capabilities).toEqual(capabilities)
    expect(handle.pid).toBe(4242)
    expect(states).toEqual(['running:http://127.0.0.1:36163'])
    expect(spawnMock.mock.calls[0][1]).toEqual([
      '--app-root',
      APP_ROOT,
      '--output',
      'ndjson',
      '--protocol',
      '1',
      'backend',
      'supervise',
      '--mode',
      'managed',
    ])

    child.stdout.feed(stoppedResultLine)
    child.close(0)
    await handle.completion
  })

  it('shutdown 写出合法控制行，并在收到 result 与进程退出后 resolve', async () => {
    const client = createClient()
    const child = mockSpawn()

    const pendingHandle = client.supervise({ mode: 'managed' })
    child.stdout.feed(helloLine)
    const handle = await pendingHandle

    const pendingShutdown = handle.shutdown({ timeoutMs: 1_000 })

    expect(child.stdin.chunks).toHaveLength(1)
    const written = child.stdin.chunks[0]
    expect(written.endsWith('\n')).toBe(true)
    const payload = JSON.parse(written.trimEnd())
    expect(Object.keys(payload).sort()).toEqual(['command', 'commandId', 'protocol'])
    expect(payload).toMatchObject({ protocol: 1, command: 'shutdown' })
    expect(payload.commandId).toMatch(/^[0-7][0-9A-HJKMNP-TV-Z]{25}$/)

    child.stdout.feed(stoppedResultLine)
    child.close(0)
    const outcome = await pendingShutdown

    expect(outcome.success).toBe(true)
    expect(outcome.result.status).toBe('stopped')
    expect(child.killed).toBe(false)
  })

  it('重复 shutdown 只写一次控制行', async () => {
    const client = createClient()
    const child = mockSpawn()

    const pendingHandle = client.supervise({ mode: 'managed' })
    child.stdout.feed(helloLine)
    const handle = await pendingHandle

    const first = handle.shutdown({ timeoutMs: 1_000 })
    const second = handle.shutdown({ timeoutMs: 1_000 })

    expect(child.stdin.chunks).toHaveLength(1)

    child.stdout.feed(stoppedResultLine)
    child.close(0)
    await Promise.all([first, second])
  })

  it('shutdown 超时才 kill，并以 RUNTIME_EXITED_UNEXPECTEDLY 收尾', async () => {
    const client = createClient()
    const child = mockSpawn()

    const pendingHandle = client.supervise({ mode: 'managed' })
    child.stdout.feed(helloLine)
    const handle = await pendingHandle

    const pendingShutdown = handle.shutdown({ timeoutMs: 20 })
    expect(child.killed).toBe(false)

    await expect(pendingShutdown).rejects.toMatchObject({
      code: 'RUNTIME_EXITED_UNEXPECTEDLY',
    })
    expect(child.killed).toBe(true)
  })
})
