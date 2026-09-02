import { spawn } from 'child_process'
import { EventEmitter } from 'node:events'
import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import {
  RuntimeClient,
  buildRuntimeArgs,
  collectRuntimeLogs,
  createCommandId,
  formatStartupLogs,
  readRuntimeBaseUrl,
  serializeControlCommand,
} from './client'
import {
  RUNTIME_CAPABILITIES,
  RUNTIME_CLIENT_ERROR_DEFINITIONS,
  RuntimeClientError,
  RuntimeEvent,
  isKnownRuntimeCapability,
  isRetryableRuntimeCode,
  lookupRuntimeErrorDefinition,
} from './protocol'

vi.mock('child_process', () => ({ spawn: vi.fn() }))
// logger 会拉起 electron-log，与本模块逻辑无关，直接替换掉。
vi.mock('../logger', () => ({
  getLogger: () => ({
    error: vi.fn(),
    warn: vi.fn(),
    info: vi.fn(),
    verbose: vi.fn(),
    debug: vi.fn(),
    silly: vi.fn(),
  }),
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

  it('offline 作为独立标志追加', () => {
    const args = buildRuntimeArgs({ runtimePath: RUNTIME_PATH, appRoot: APP_ROOT, offline: true }, [
      'doctor',
    ])

    expect(args).toContain('--offline')
    expect(args.at(-1)).toBe('doctor')
  })
})

describe('createCommandId', () => {
  it('生成 Runtime validOperationID 认可的 26 位 ULID', () => {
    const id = createCommandId(1_767_000_000_000)

    // Runtime 要求：长度 26、Crockford base32 字母表、首字符不大于 '7'。
    expect(id).toHaveLength(26)
    expect(id).toMatch(/^[0-7][0-9A-HJKMNP-TV-Z]{25}$/)
  })

  it('同一毫秒内也不重复', () => {
    const ids = new Set(Array.from({ length: 200 }, () => createCommandId(1_767_000_000_000)))

    expect(ids.size).toBe(200)
  })
})

describe('serializeControlCommand', () => {
  it('每行一个 JSON 对象且必须以换行结尾', () => {
    const text = serializeControlCommand({
      protocol: 1,
      command: 'cancel',
      commandId: '01M1F6TJTKFC1M6DWM8C9AXZCK',
    })

    expect(text).toBe(
      '{"protocol":1,"command":"cancel","commandId":"01M1F6TJTKFC1M6DWM8C9AXZCK"}\n'
    )
  })
})

describe('formatStartupLogs', () => {
  it('沿用 backendService 的整块展示格式', () => {
    expect(formatStartupLogs(['第一行', '第二行'], ['报错'])).toBe(
      '[stdout]\n第一行\n第二行\n\n[stderr]\n报错'
    )
  })

  it('单侧为空时只输出另一侧，两侧都空返回 undefined', () => {
    expect(formatStartupLogs(['只有标准输出'], [])).toBe('[stdout]\n只有标准输出')
    expect(formatStartupLogs([], ['只有标准错误'])).toBe('[stderr]\n只有标准错误')
    expect(formatStartupLogs([], [])).toBeUndefined()
    expect(formatStartupLogs(['  ', ''], ['\n'])).toBeUndefined()
  })
})

describe('collectRuntimeLogs', () => {
  it('按 operationId 分组，stdout 与 stderr 各自保序', () => {
    const events = [
      { type: 'log', operationId: 'A', stream: 'stdout', message: 'a1' },
      { type: 'log', operationId: 'A', stream: 'stderr', message: 'e1' },
      { type: 'log', operationId: 'B', stream: 'stdout', message: 'b1' },
      { type: 'log', operationId: 'A', stream: 'stdout', message: 'a2' },
      { type: 'log', operationId: 'A', stream: 'unknown', message: 'x1' },
    ] as unknown as RuntimeEvent[]

    expect(collectRuntimeLogs(events)).toEqual({
      A: { stdout: ['a1', 'a2'], stderr: ['e1'], other: ['x1'] },
      B: { stdout: ['b1'], stderr: [], other: [] },
    })
  })
})

describe('readRuntimeBaseUrl', () => {
  it('从 details 读取后端基地址，缺失时返回 undefined', () => {
    expect(readRuntimeBaseUrl({ baseUrl: 'http://127.0.0.1:36163' })).toBe('http://127.0.0.1:36163')
    expect(readRuntimeBaseUrl({})).toBeUndefined()
    expect(readRuntimeBaseUrl({ baseUrl: '' })).toBeUndefined()
    expect(readRuntimeBaseUrl({ baseUrl: 36163 })).toBeUndefined()
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

  it('doctor 的进度事件全部透出，终态仍为成功', async () => {
    const client = createClient()
    const child = mockSpawn()
    const seen: RuntimeEvent[] = []

    const pending = client.run(['doctor'], { onEvent: event => seen.push(event) })
    child.stdout.feed(fixture('doctor.ndjson'))
    child.close(0)
    const outcome = await pending

    expect(seen).toHaveLength(21)
    expect(outcome.events.filter(event => event.type === 'progress')).toHaveLength(19)
    expect(outcome.success).toBe(true)
    expect(outcome.result.stage).toBe('doctor')
  })

  it('半行分片到达时能正确拼接', async () => {
    const client = createClient()
    const child = mockSpawn()
    const raw = fixture('version.ndjson')
    const cut = Math.floor(raw.length / 3)

    const pending = client.run(['version'])
    child.stdout.feed(raw.slice(0, cut))
    child.stdout.feed(raw.slice(cut, cut * 2))
    child.stdout.feed(raw.slice(cut * 2))
    child.close(0)

    await expect(pending).resolves.toMatchObject({ success: true, code: 'OK' })
  })

  it('失败 result 不抛异常，由调用方读 result.code', async () => {
    const client = createClient()
    const child = mockSpawn()

    const pending = client.run(['backend', 'supervise'])
    child.stdout.feed(fixture('supervise-invalid-mode.ndjson'))
    child.close(2)
    const outcome = await pending

    expect(outcome.success).toBe(false)
    expect(outcome.code).toBe('INVALID_ARGUMENT')
    expect(outcome.errors).toHaveLength(1)
    expect(outcome.result.remediation).toEqual(['run-doctor'])
    // 退出码只做粗分类，精确原因看 result.code。
    expect(outcome.exitCode).toBe(2)
  })

  it('可重试的 Runtime 失败照样正常返回，retryable 与 remediation 取自 result', async () => {
    const client = createClient()
    const child = mockSpawn()

    const pending = client.run(['dependencies', 'check'])
    child.stdout.feed(fixture('dependencies-check-failed.ndjson'))
    child.close(40)
    const outcome = await pending

    expect(outcome.success).toBe(false)
    expect(outcome.code).toBe('GIT_REPOSITORY_INVALID')
    expect(outcome.result.retryable).toBe(true)
    expect(outcome.result.remediation).toEqual(['retry-sync'])
    expect(isRetryableRuntimeCode('GIT_REPOSITORY_INVALID')).toBe(true)
    // hello.capabilities 随命令变化，不能从命令名推断。
    expect(outcome.hello.capabilities).toEqual(['stdin.cancel'])
  })

  it('warning 单独归集并保留在 result.details.warnings 里', async () => {
    const client = createClient()
    const child = mockSpawn()

    const pending = client.run(['dependencies', 'check'])
    child.stdout.feed(fixture('cancelled-with-warning.ndjson'))
    child.close(130)
    const outcome = await pending

    expect(outcome.warnings.map(item => item.code)).toEqual(['INVALID_CONTROL_COMMAND'])
    expect(outcome.code).toBe('OPERATION_CANCELLED')
    expect(outcome.result.details.warningCount).toBe(1)
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

  it('协议不匹配时 Runtime 只给退出码 10 和 stderr，同样归为 RUNTIME_PROTOCOL_MISMATCH', async () => {
    // 实测行为：--protocol 2 时 stdout 全空，没有 hello/result，
    // stderr 一行诊断，退出码 10。见 __fixtures__/protocol-2-mismatch.stderr.txt。
    const client = createClient()
    const child = mockSpawn()
    const stderr = fixture('protocol-2-mismatch.stderr.txt')

    const pending = client.run(['version'])
    child.stderr.feed(stderr)
    child.close(10)

    await expect(pending).rejects.toMatchObject({
      code: 'RUNTIME_PROTOCOL_MISMATCH',
      details: { exitCode: 10, stderr },
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

  it('未知子命令这类参数错误也走 RUNTIME_EXITED_UNEXPECTEDLY', async () => {
    // 实测：未知子命令 stdout 全空、stderr 一行诊断、退出码 2，不承诺 hello/result。
    const client = createClient()
    const child = mockSpawn()

    const pending = client.run(['nosuchcmd'])
    child.stderr.feed(fixture('unknown-command.stderr.txt'))
    child.close(2)

    await expect(pending).rejects.toMatchObject({
      code: 'RUNTIME_EXITED_UNEXPECTEDLY',
      details: { exitCode: 2 },
    })
  })

  it('可执行文件不存在时报 RUNTIME_NOT_FOUND 且不 spawn', async () => {
    const client = createClient({ runtimePath: join(fixturesDir, '不存在的-runtime.exe') })

    await expect(client.run(['version'])).rejects.toMatchObject({ code: 'RUNTIME_NOT_FOUND' })
    expect(spawnMock).not.toHaveBeenCalled()
  })

  it('spawn 抛错时按 errno 区分 RUNTIME_NOT_FOUND 与 RUNTIME_SPAWN_FAILED', async () => {
    const client = createClient()

    const denied = mockSpawn()
    const deniedPending = client.run(['version'])
    denied.emit('error', Object.assign(new Error('permission denied'), { code: 'EACCES' }))
    await expect(deniedPending).rejects.toMatchObject({ code: 'RUNTIME_SPAWN_FAILED' })

    const missing = mockSpawn()
    const missingPending = client.run(['version'])
    missing.emit('error', Object.assign(new Error('no such file'), { code: 'ENOENT' }))
    await expect(missingPending).rejects.toMatchObject({ code: 'RUNTIME_NOT_FOUND' })
  })

  it('log 事件按 operationId 聚合，可直接喂给 formatStartupLogs', async () => {
    // log 事件只在 backend supervise 转发受管进程输出时出现，这里用协议结构合成。
    const client = createClient()
    const child = mockSpawn()
    const operationId = '01M1F6M33JFZZ7Y85BE5S849ZN'
    const base = { protocol: 1, operationId, timestamp: '2026-09-01T21:20:03.442+02:00' }

    const pending = client.run(['backend', 'supervise'])
    child.stdout.feed(
      [
        line({
          ...base,
          type: 'hello',
          sequence: 1,
          runtimeVersion: 'dev',
          command: 'backend supervise',
          capabilities: ['stdin.cancel', 'state.v1', 'log.stream'],
        }),
        line({
          ...base,
          type: 'log',
          sequence: 2,
          source: 'backend',
          stream: 'stdout',
          message: 'INFO 启动中',
        }),
        line({
          ...base,
          type: 'log',
          sequence: 3,
          source: 'backend',
          stream: 'stderr',
          message: 'Traceback',
        }),
        line({
          ...base,
          type: 'log',
          sequence: 4,
          source: 'backend',
          stream: 'stdout',
          message: 'INFO 就绪',
        }),
        line({
          ...base,
          type: 'result',
          sequence: 5,
          success: true,
          code: 'OK',
          stage: 'backend.shutdown',
          status: 'stopped',
          message: '后端已停止',
          retryable: false,
          remediation: [],
          details: {},
        }),
      ].join('')
    )
    child.close(0)
    const outcome = await pending

    expect(outcome.logs[operationId]).toEqual({
      stdout: ['INFO 启动中', 'INFO 就绪'],
      stderr: ['Traceback'],
      other: [],
    })
    expect(
      formatStartupLogs(outcome.logs[operationId].stdout, outcome.logs[operationId].stderr)
    ).toBe('[stdout]\nINFO 启动中\nINFO 就绪\n\n[stderr]\nTraceback')
  })

  it('INTERNAL_ERROR 按不可重试处理，且与 OUTPUT_WRITE_FAILED 文案不同', async () => {
    const client = createClient()
    const child = mockSpawn()
    const base = {
      protocol: 1,
      operationId: '01M1F6M33JFZZ7Y85BE5S849ZN',
      timestamp: '2026-09-01T21:20:03.442+02:00',
    }

    const pending = client.run(['repair'])
    child.stdout.feed(
      [
        line({
          ...base,
          type: 'hello',
          sequence: 1,
          runtimeVersion: 'dev',
          command: 'repair',
          capabilities: ['stdin.cancel'],
        }),
        line({
          ...base,
          type: 'result',
          sequence: 2,
          success: false,
          code: 'INTERNAL_ERROR',
          stage: 'repair',
          status: 'failed',
          message: '内部错误',
          retryable: false,
          remediation: ['open-log', 'contact-support'],
          details: {},
        }),
      ].join('')
    )
    child.close(20)
    const outcome = await pending

    expect(outcome.success).toBe(false)
    expect(outcome.result.retryable).toBe(false)
    expect(isRetryableRuntimeCode('INTERNAL_ERROR')).toBe(false)

    const internal = lookupRuntimeErrorDefinition('INTERNAL_ERROR')
    const outputWrite = lookupRuntimeErrorDefinition('OUTPUT_WRITE_FAILED')
    expect(internal).toMatchObject({
      retryable: false,
      exitCode: 20,
      remediation: ['open-log', 'contact-support'],
    })
    // 两者行为四元组相同，文案必须区分「Runtime 有 bug」与「输出通道坏了」。
    expect(internal?.remediation).toEqual(outputWrite?.remediation)
    expect(internal?.summary).not.toBe(outputWrite?.summary)
  })

  it('未知错误码按不可重试兜底', () => {
    expect(isRetryableRuntimeCode('SOME_FUTURE_CODE')).toBe(false)
    expect(lookupRuntimeErrorDefinition('SOME_FUTURE_CODE')).toBeUndefined()
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

  function logLine(sequence: number, stream: 'stdout' | 'stderr', message: string): string {
    return line({ ...base, type: 'log', sequence, source: 'backend', stream, message })
  }

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

  it('development 模式带上 --repo', async () => {
    const client = createClient()
    const child = mockSpawn()

    const pendingHandle = client.supervise({ mode: 'development', repo: 'D:\\src\\AUTO-MAS' })
    child.stdout.feed(helloLine)
    const handle = await pendingHandle

    expect(spawnMock.mock.calls[0][1].slice(-4)).toEqual([
      '--mode',
      'development',
      '--repo',
      'D:\\src\\AUTO-MAS',
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

  it('status 与 cancel 各自生成独立 commandId', async () => {
    const client = createClient()
    const child = mockSpawn()

    const pendingHandle = client.supervise({ mode: 'managed' })
    child.stdout.feed(helloLine)
    const handle = await pendingHandle

    const statusId = handle.status()
    const cancelId = handle.cancel()

    expect(statusId).not.toBe(cancelId)
    expect(child.stdin.chunks.map(chunk => JSON.parse(chunk.trimEnd()).command)).toEqual([
      'status',
      'cancel',
    ])

    child.stdout.feed(stoppedResultLine)
    child.close(0)
    await handle.completion
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

  it('hello 未宣告 stdin.shutdown 时 shutdown 不发命令、不等超时，直接 kill', async () => {
    const client = createClient()
    const child = mockSpawn()

    const pendingHandle = client.supervise({ mode: 'managed' })
    child.stdout.feed(
      line({
        ...base,
        type: 'hello',
        sequence: 1,
        runtimeVersion: 'dev',
        command: 'backend supervise',
        capabilities: ['stdin.cancel', 'state.v1', 'log.stream'],
      })
    )
    const handle = await pendingHandle

    // 超时给得很长：若走了等待路径，这里会一直挂着直到 vitest 自己超时。
    const pendingShutdown = handle.shutdown({ timeoutMs: 600_000 })

    expect(child.stdin.chunks).toEqual([])
    expect(child.killed).toBe(true)
    await expect(pendingShutdown).rejects.toMatchObject({
      code: 'RUNTIME_EXITED_UNEXPECTEDLY',
      details: { signal: 'SIGTERM' },
    })
  })

  it('log 事件只保留最近 N 条，不进 events，可通过句柄随时读取', async () => {
    const client = createClient()
    const child = mockSpawn()
    const seen: string[] = []

    const pendingHandle = client.supervise({
      mode: 'managed',
      recentLogCapacity: 3,
      onLog: event => seen.push(event.message),
    })
    child.stdout.feed(helloLine)
    const handle = await pendingHandle

    child.stdout.feed(runningStateLine)
    for (let i = 1; i <= 5; i += 1) {
      child.stdout.feed(logLine(10 + i, i === 4 ? 'stderr' : 'stdout', `第 ${i} 行`))
    }

    // 回调仍逐条收到；缓冲只留最近三条。
    expect(seen).toEqual(['第 1 行', '第 2 行', '第 3 行', '第 4 行', '第 5 行'])
    expect(handle.recentLogs().map(event => event.message)).toEqual([
      '第 3 行',
      '第 4 行',
      '第 5 行',
    ])
    // 返回的是副本，改它不影响内部缓冲。
    handle.recentLogs().length = 0
    expect(handle.recentLogs()).toHaveLength(3)

    child.stdout.feed(stoppedResultLine)
    child.close(0)
    const outcome = await handle.completion

    expect(outcome.events.map(event => event.type)).toEqual(['hello', 'state', 'result'])
    expect(outcome.recentLogs.map(event => event.message)).toEqual([
      '第 3 行',
      '第 4 行',
      '第 5 行',
    ])
    expect(outcome.logs[operationId]).toEqual({
      stdout: ['第 3 行', '第 5 行'],
      stderr: ['第 4 行'],
      other: [],
    })
  })

  it('握手后的坏行不掀翻正在运行的后端，只记录并回调', async () => {
    const client = createClient()
    const child = mockSpawn()
    const protocolErrors: RuntimeClientError[] = []

    const pendingHandle = client.supervise({
      mode: 'managed',
      onProtocolError: error => protocolErrors.push(error),
    })
    child.stdout.feed(helloLine)
    const handle = await pendingHandle

    child.stdout.feed('这行不是 JSON\n')
    expect(protocolErrors).toHaveLength(1)
    expect(protocolErrors[0].code).toBe('RUNTIME_PROTOCOL_ERROR')
    expect(child.killed).toBe(false)

    child.stdout.feed(stoppedResultLine)
    child.close(0)
    const outcome = await handle.completion

    expect(outcome.success).toBe(true)
    expect(outcome.protocolErrors).toHaveLength(1)
  })

  it('onEvent 订阅可取消', async () => {
    const client = createClient()
    const child = mockSpawn()
    const seen: string[] = []

    const pendingHandle = client.supervise({ mode: 'managed' })
    child.stdout.feed(helloLine)
    const handle = await pendingHandle

    const unsubscribe = handle.onEvent(event => seen.push(event.type))
    child.stdout.feed(runningStateLine)
    unsubscribe()
    child.stdout.feed(stoppedResultLine)
    child.close(0)
    await handle.completion

    expect(seen).toEqual(['state'])
  })
})

describe('RUNTIME_CAPABILITIES', () => {
  it('与 Runtime 侧 values.go 的五项能力一致', () => {
    expect(RUNTIME_CAPABILITIES).toEqual([
      'stdin.cancel',
      'state.v1',
      'log.stream',
      'stdin.shutdown',
      'stdin.status',
    ])
    expect(isKnownRuntimeCapability('stdin.shutdown')).toBe(true)
    expect(isKnownRuntimeCapability('stdin.status')).toBe(true)
    expect(isKnownRuntimeCapability('stdin.future')).toBe(false)
  })
})

describe('RuntimeClientError', () => {
  it('六个调用侧错误码都有 retryable 与 remediation 定义', () => {
    const codes = Object.keys(RUNTIME_CLIENT_ERROR_DEFINITIONS)

    expect(codes.sort()).toEqual([
      'RUNTIME_EXITED_UNEXPECTEDLY',
      'RUNTIME_HANDSHAKE_TIMEOUT',
      'RUNTIME_NOT_FOUND',
      'RUNTIME_PROTOCOL_ERROR',
      'RUNTIME_PROTOCOL_MISMATCH',
      'RUNTIME_SPAWN_FAILED',
    ])
    for (const definition of Object.values(RUNTIME_CLIENT_ERROR_DEFINITIONS)) {
      expect(definition.remediation.length).toBeGreaterThan(0)
      expect(definition.summary).not.toBe('')
    }
  })

  it('未给 message 时回落到该错误码的固定摘要', () => {
    const error = new RuntimeClientError('RUNTIME_NOT_FOUND')

    expect(error.name).toBe('RuntimeClientError')
    expect(error.message).toBe('找不到 Runtime 可执行文件')
    expect(error.retryable).toBe(false)
  })
})
