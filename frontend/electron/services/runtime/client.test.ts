import { spawn } from 'child_process'
import { EventEmitter, once } from 'node:events'
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vite-plus/test'

import { RuntimeClient, buildRuntimeArgs } from './client'
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

describe('一次性命令退出', () => {
  it('握手超时后等到真实 close 才报告可重新启动', async () => {
    vi.useFakeTimers()
    const client = createClient()
    const child = mockSpawn()
    child.kill = () => {
      child.killed = true
      return true
    }
    let finished = false
    const pending = client.run(['workspace', 'check'], { handshakeTimeoutMs: 20 })
    void pending.then(
      () => {
        finished = true
      },
      () => {
        finished = true
      }
    )
    await vi.advanceTimersByTimeAsync(20)
    expect(child.killed).toBe(true)
    const finishedBeforeClose = finished
    expect(client.hasActiveSessions).toBe(true)
    child.close(7)
    await expect(pending).rejects.toMatchObject({
      code: 'RUNTIME_HANDSHAKE_TIMEOUT',
      details: { command: 'workspace check', processExited: true, exitCode: 7 },
    })
    expect(finishedBeforeClose).toBe(false)
    expect(client.hasActiveSessions).toBe(false)
  })

  it('无法确认退出时有界失败，迟到 hello 不交出控制权并保留进程供再次清理', async () => {
    vi.useFakeTimers()
    const client = createClient()
    const child = mockSpawn()
    child.kill = () => {
      child.killed = true
      return true
    }
    const onStarted = vi.fn()
    const pending = client
      .run(['workspace', 'check'], { handshakeTimeoutMs: 20, onStarted })
      .catch(error => error)
    await vi.advanceTimersByTimeAsync(2020)
    expect(await pending).toMatchObject({
      code: 'RUNTIME_HANDSHAKE_TIMEOUT',
      details: { command: 'workspace check', processExited: false, exitCode: null },
    })
    child.stdout.feed(fixture('version.ndjson'))
    expect(onStarted).not.toHaveBeenCalled()
    expect(client.hasActiveSessions).toBe(true)
    child.close(0)
    expect(await client.stop()).toBeUndefined()
    expect(client.hasActiveSessions).toBe(false)
  })

  it('supervise 握手前同样归客户端持有并在退出时回收', async () => {
    vi.useFakeTimers()
    const client = createClient()
    const child = mockSpawn()
    const pending = client.supervise({ mode: 'managed' }).catch(error => error)
    const stopping = client.stop(20)
    await vi.advanceTimersByTimeAsync(20)
    await stopping
    const killedByStop = child.killed
    if (!killedByStop) child.close(null, 'SIGKILL')
    expect(await pending).toMatchObject({
      code: 'RUNTIME_EXITED_UNEXPECTEDLY',
      details: { command: 'backend supervise', processExited: true },
    })
    expect(killedByStop).toBe(true)
    expect(client.hasActiveSessions).toBe(false)
    await expect(client.supervise({ mode: 'managed' })).rejects.toBeInstanceOf(Error)
    expect(spawnMock).toHaveBeenCalledTimes(1)
  })

  it('supervise 未确认退出时保留同一进程，下一次 stop 继续回收', async () => {
    vi.useFakeTimers()
    const client = createClient()
    const child = mockSpawn()
    const terminate = vi.spyOn(child, 'kill').mockImplementation(() => {
      child.killed = true
      return true
    })
    const pending = client
      .supervise({ mode: 'managed', handshakeTimeoutMs: 1 })
      .catch(error => error)
    const firstStop = client.stop(0).catch(error => error)
    await vi.advanceTimersByTimeAsync(2001)
    expect(await firstStop).toMatchObject({ code: 'RUNTIME_EXITED_UNEXPECTEDLY' })
    expect(await pending).toMatchObject({
      code: 'RUNTIME_HANDSHAKE_TIMEOUT',
      details: { command: 'backend supervise', processExited: false },
    })
    expect(client.hasActiveSessions).toBe(true)

    const secondStop = client.stop(0)
    await vi.advanceTimersByTimeAsync(0)
    expect(terminate).toHaveBeenCalledTimes(2)
    child.close(0)
    await secondStop
    expect(client.hasActiveSessions).toBe(false)
    expect(spawnMock).toHaveBeenCalledTimes(1)
  })

  it('握手前也持有并回收命令进程，关闭后不能再派生命令', async () => {
    const client = createClient()
    const child = mockSpawn()
    const work = client.run(['bootstrap']).catch(() => undefined)
    await client.stop(20)
    await work
    expect(child.killed).toBe(true)
    expect(client.hasActiveSessions).toBe(false)
    await expect(client.run(['doctor'])).rejects.toBeInstanceOf(Error)
    expect(spawnMock).toHaveBeenCalledTimes(1)
  })

  it.each(['ignore-cancel', 'finish-commit'])(
    '原生子进程 %s 时确认真实退出并保留终态',
    async behavior => {
      const { spawn: nativeSpawn } =
        await vi.importActual<typeof import('child_process')>('child_process')
      const root = mkdtempSync(join(tmpdir(), 'mas-runtime-stop-'))
      const script = join(root, 'runtime.cjs')
      const lines = fixture('bootstrap-success.ndjson').trim().split('\n')
      writeFileSync(
        script,
        `
      process.stdout.write(${JSON.stringify(lines[0] + '\n')});
      let finishing = false;
      process.stdin.on('data', () => {
        if (${JSON.stringify(behavior === 'finish-commit')} && !finishing) {
          finishing = true;
          setTimeout(() => process.stdout.write(${JSON.stringify(lines.slice(1).join('\n') + '\n')}, () => process.exit(0)), 30);
        }
      });
      setInterval(() => {}, 1000);
    `
      )
      let child: ReturnType<typeof nativeSpawn> | undefined
      spawnMock.mockImplementation((_command, _args, options) => {
        child = nativeSpawn(process.execPath, [script], options)
        return child as never
      })
      const client = createClient()
      let started!: () => void
      const ready = new Promise<void>(resolve => {
        started = resolve
      })
      const work = client.run(['bootstrap'], { onStarted: () => started() }).catch(() => null)
      try {
        await ready
        await client.stop(200)
        const outcome = await work
        expect(client.hasActiveSessions).toBe(false)
        expect(child!.exitCode !== null || child!.signalCode !== null).toBe(true)
        if (behavior === 'finish-commit') {
          expect(outcome).toMatchObject({ success: true })
          expect(child!.killed).toBe(false)
        } else {
          expect(outcome).toBeNull()
          expect(child!.killed).toBe(true)
        }
      } finally {
        if (child && child.exitCode === null && child.signalCode === null) {
          const exited = once(child, 'close')
          child.kill('SIGKILL')
          await exited
        }
        rmSync(root, { recursive: true, force: true })
      }
    }
  )
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
  it.each(['silent', 'stderr'])(
    '原生子进程 %s 的 hello 超时确认真实退出，并记录首输出是否到达',
    async behavior => {
      vi.useFakeTimers()
      const { spawn: nativeSpawn } =
        await vi.importActual<typeof import('child_process')>('child_process')
      let child: ReturnType<typeof nativeSpawn> | undefined
      spawnMock.mockImplementation((_command, _args, options) => {
        child = nativeSpawn(
          process.execPath,
          [
            '-e',
            `
          if (${JSON.stringify(behavior === 'stderr')}) process.stderr.write('private diagnostic');
          setInterval(() => {}, 1000);
        `,
          ],
          options
        )
        return child as never
      })
      try {
        const client = createClient()
        const pending = client
          .run(['workspace', 'check'], { handshakeTimeoutMs: 20 })
          .catch(error => error)
        // 真实管道或 spawn 事件作同步点，超时由假时钟触发，不依赖机器启动 Node 的速度。
        await once(
          behavior === 'stderr' ? child!.stderr! : child!,
          behavior === 'stderr' ? 'data' : 'spawn'
        )
        await vi.advanceTimersByTimeAsync(20)
        expect(await pending).toMatchObject({
          code: 'RUNTIME_HANDSHAKE_TIMEOUT',
          details: { command: 'workspace check', processExited: true },
        })
        expect(client.hasActiveSessions).toBe(false)
        expect(child!.exitCode !== null || child!.signalCode !== null).toBe(true)
        const diagnostics = loggerMock.info.mock.calls
          .map(([message]) => String(message))
          .filter(message => message.startsWith('[Runtime进程] '))
          .map(message => JSON.parse(message.slice('[Runtime进程] '.length)))
        const timeout = diagnostics.find(item => item.event === 'handshake_timeout')
        expect(timeout).toMatchObject({
          command: 'workspace check',
          stdoutBytes: 0,
          timeoutMs: 20,
        })
        expect(timeout.stderrBytes > 0).toBe(behavior === 'stderr')
        expect(timeout.timeoutCallbackDelayMs).toBeGreaterThanOrEqual(0)
        expect(diagnostics.some(item => item.event === 'spawned' && item.pid === child!.pid)).toBe(
          true
        )
        expect(diagnostics.at(-1)).toMatchObject({ event: 'close', processExited: true })
      } finally {
        if (child && child.exitCode === null && child.signalCode === null) {
          const exited = once(child, 'close')
          child.kill('SIGKILL')
          await exited
        }
      }
    }
  )

  it('创建进程被拒时保留系统错误，并区分 error 与实际 close', async () => {
    const child = mockSpawn()
    const client = createClient()
    const pending = client.run(['workspace', 'check'])
    child.emit('error', Object.assign(new Error('access denied'), { code: 'EACCES' }))
    await expect(pending).rejects.toMatchObject({
      code: 'RUNTIME_SPAWN_FAILED',
      message: '启动 Runtime 失败：access denied',
      cause: { code: 'EACCES' },
      details: { command: 'workspace check', processExited: true },
    })
    const diagnostics = loggerMock.info.mock.calls
      .map(([message]) => String(message))
      .filter(message => message.startsWith('[Runtime进程] '))
      .map(message => JSON.parse(message.slice('[Runtime进程] '.length)))
    expect(diagnostics.map(item => item.event)).toEqual(['spawn_requested', 'spawn_error', 'close'])
    expect(diagnostics[1]).toMatchObject({ systemCode: 'EACCES' })
  })

  it('本地诊断关联创建、首输出、hello 与退出，不记录输出或命令参数', async () => {
    const client = createClient()
    const child = mockSpawn()
    const pending = client.run(['version', '--private', 'private-argument'])
    child.emit('spawn')
    child.stderr.feed('private-stderr')
    child.stderr.feed('more-private-stderr')
    child.stdout.feed(fixture('version.ndjson'))
    child.emit('exit', 0, null)
    child.close(0)
    await pending
    const diagnostics = loggerMock.info.mock.calls
      .map(([message]) => String(message))
      .filter(message => message.startsWith('[Runtime进程] '))
      .map(message => JSON.parse(message.slice('[Runtime进程] '.length)))
    expect(diagnostics.map(item => item.event)).toEqual([
      'spawn_requested',
      'spawned',
      'first_stderr',
      'first_stdout',
      'hello',
      'exit',
      'close',
    ])
    expect(new Set(diagnostics.map(item => item.sessionId)).size).toBe(1)
    expect(diagnostics.every(item => item.command === 'version' && item.elapsedMs >= 0)).toBe(true)
    expect(diagnostics.find(item => item.event === 'spawned')).toMatchObject({ pid: 4242 })
    expect(diagnostics.find(item => item.event === 'close')).toMatchObject({
      processExited: true,
      exitCode: 0,
      signal: null,
      stderrBytes: Buffer.byteLength('private-stderrmore-private-stderr'),
    })
    const logged = JSON.stringify(diagnostics)
    expect(logged).not.toContain('private-argument')
    expect(logged).not.toContain('private-stderr')
    expect(logged).not.toContain(APP_ROOT)
    expect(logged).not.toContain(RUNTIME_PATH)
  })

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

  it('握手前的 stop 在 hello 到达后使用 shutdown，句柄接手不重复发送', async () => {
    const client = createClient()
    const child = mockSpawn()
    const pending = client.supervise({ mode: 'managed' })
    const stopping = client.stop(1000)
    child.stdout.feed(helloLine)
    const handle = await pending
    const handleStop = handle.shutdown({ timeoutMs: 1000 })
    const commandsBeforeClose = child.stdin.chunks.map(chunk => JSON.parse(chunk).command)
    child.stdout.feed(stoppedResultLine)
    child.close(0)
    await stopping
    await handleStop
    expect(commandsBeforeClose).toEqual(['shutdown'])
    expect(client.hasActiveSessions).toBe(false)
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
