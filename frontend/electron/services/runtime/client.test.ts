import { spawn } from 'child_process'
import { EventEmitter, once } from 'node:events'
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vite-plus/test'

import { RuntimeClient } from './client'
import { RuntimeClientError } from './protocol'

vi.mock('child_process', () => ({ spawn: vi.fn() }))
// logger 会拉起 electron-log，与本模块逻辑无关，直接替换掉；共用一个实例以便断言日志调用。
const loggerMock = vi.hoisted(() => ({
  error: vi.fn(),
  warn: vi.fn(),
  info: vi.fn(),
  debug: vi.fn(),
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
  destroyed = false
  writableEnded = false

  write(): boolean {
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
  it('无法确认退出时有界失败，迟到 hello 不交出控制权并保留进程供再次清理', async () => {
    vi.useFakeTimers()
    const versionLines = fixture('version.ndjson').trim().split('\n')
    const hello = JSON.parse(versionLines[0])
    for (const kind of ['run', 'supervise'] as const) {
      const command = kind === 'run' ? 'workspace check' : 'backend supervise'
      const lateOutput =
        line({ ...hello, command, capabilities: ['stdin.cancel', 'stdin.shutdown'] }) +
        line({
          protocol: 1,
          type: 'state',
          operationId: hello.operationId,
          sequence: 2,
          timestamp: hello.timestamp,
          stage: 'backend.run',
          status: 'running',
          message: 'ready',
          details: { baseUrl: 'http://127.0.0.1:37491' },
        }) +
        `${versionLines[2]}\n`

      // close 到达前都归客户端持有；有界失败也不能把未退出进程当成可重启。
      for (const confirmsClose of [true, false]) {
        const client = createClient()
        const child = mockSpawn()
        const terminate = vi.spyOn(child, 'kill').mockImplementation(() => {
          child.killed = true
          return true
        })
        const spawnsBefore = spawnMock.mock.calls.length
        const onStarted = vi.fn()
        const onEvent = vi.fn()
        const onState = vi.fn()
        const options = { handshakeTimeoutMs: 20, onStarted, onEvent, onState }
        let finished = false
        const pending = (
          kind === 'run'
            ? client.run(['workspace', 'check'], options)
            : client.supervise({ mode: 'managed', ...options })
        )
          .catch(error => error)
          .finally(() => {
            finished = true
          })
        expect(client.hasActiveSessions).toBe(true)
        await vi.advanceTimersByTimeAsync(20)
        expect(terminate).toHaveBeenCalledTimes(1)
        expect(finished).toBe(false)
        child.stdout.feed(lateOutput)
        await Promise.resolve()
        expect(onStarted).not.toHaveBeenCalled()
        expect(onEvent).not.toHaveBeenCalled()
        expect(onState).not.toHaveBeenCalled()
        expect(client.hasActiveSessions).toBe(true)

        if (confirmsClose) {
          child.close(7)
          expect(await pending).toMatchObject({
            code: 'RUNTIME_HANDSHAKE_TIMEOUT',
            details: { command, processExited: true, exitCode: 7 },
          })
        } else {
          await vi.advanceTimersByTimeAsync(2000)
          expect(await pending).toMatchObject({
            code: 'RUNTIME_HANDSHAKE_TIMEOUT',
            details: { command, processExited: false, exitCode: null },
          })
          child.stdout.feed(lateOutput)
          expect(onStarted).not.toHaveBeenCalled()
          expect(onEvent).not.toHaveBeenCalled()
          expect(onState).not.toHaveBeenCalled()
          expect(client.hasActiveSessions).toBe(true)
          const firstStop = client.stop(0).catch(error => error)
          await vi.advanceTimersByTimeAsync(2000)
          expect(await firstStop).toMatchObject({ code: 'RUNTIME_EXITED_UNEXPECTEDLY' })
          expect(client.hasActiveSessions).toBe(true)
          await expect(client.run(['doctor'])).rejects.toBeInstanceOf(Error)
          await expect(client.supervise({ mode: 'managed' })).rejects.toBeInstanceOf(Error)
          expect(spawnMock).toHaveBeenCalledTimes(spawnsBefore + 1)

          let stopped = false
          const secondStop = client.stop(0).then(() => {
            stopped = true
          })
          await vi.advanceTimersByTimeAsync(0)
          expect(terminate).toHaveBeenCalledTimes(3)
          expect(stopped).toBe(false)
          child.close(0)
          await secondStop
          await client.stop(0)
          expect(terminate).toHaveBeenCalledTimes(3)
        }
        expect(client.hasActiveSessions).toBe(false)
        expect(spawnMock).toHaveBeenCalledTimes(spawnsBefore + 1)
      }

      const client = createClient()
      const child = mockSpawn()
      const spawnsBefore = spawnMock.mock.calls.length
      const pending = (
        kind === 'run' ? client.run(['bootstrap']) : client.supervise({ mode: 'managed' })
      ).catch(error => error)
      expect(client.hasActiveSessions).toBe(true)
      const stopping = client.stop(20)
      await vi.advanceTimersByTimeAsync(20)
      await stopping
      expect(await pending).toMatchObject({
        code: 'RUNTIME_EXITED_UNEXPECTEDLY',
        details: { command: kind === 'run' ? 'bootstrap' : command, processExited: true },
      })
      expect(child.killed).toBe(true)
      expect(client.hasActiveSessions).toBe(false)
      await expect(client.run(['doctor'])).rejects.toBeInstanceOf(Error)
      await expect(client.supervise({ mode: 'managed' })).rejects.toBeInstanceOf(Error)
      expect(spawnMock).toHaveBeenCalledTimes(spawnsBefore + 1)
    }

    const deniedClient = createClient()
    const deniedChild = mockSpawn()
    deniedChild.kill = () => true
    let deniedFinished = false
    const denied = deniedClient
      .run(['workspace', 'check'])
      .catch(error => error)
      .finally(() => {
        deniedFinished = true
      })
    deniedChild.emit('error', Object.assign(new Error('access denied'), { code: 'EACCES' }))
    await vi.advanceTimersByTimeAsync(0)
    expect(deniedFinished).toBe(false)
    expect(deniedClient.hasActiveSessions).toBe(true)
    deniedChild.close(-13)
    expect(await denied).toMatchObject({
      code: 'RUNTIME_SPAWN_FAILED',
      cause: { code: 'EACCES' },
      details: { processExited: true, exitCode: -13 },
    })
    expect(deniedClient.hasActiveSessions).toBe(false)

    const exitedClient = createClient()
    const exitedChild = mockSpawn()
    const exited = exitedClient.run(['doctor'])
    exitedChild.stdout.feed(line({ ...hello, command: 'doctor' }))
    exitedChild.stderr.feed('panic: 崩了\n')
    exitedChild.close(50)
    await expect(exited).rejects.toMatchObject({
      code: 'RUNTIME_EXITED_UNEXPECTEDLY',
      details: { processExited: true, exitCode: 50 },
    })
    expect(exitedClient.hasActiveSessions).toBe(false)

    const { spawn: nativeSpawn } =
      await vi.importActual<typeof import('child_process')>('child_process')
    let nativeChild: ReturnType<typeof nativeSpawn> | undefined
    spawnMock.mockImplementation((_command, _args, options) => {
      nativeChild = nativeSpawn(
        process.execPath,
        ['-e', "process.stderr.write('private diagnostic'); setInterval(() => {}, 1000);"],
        options
      )
      return nativeChild as never
    })
    try {
      const client = createClient()
      const pending = client
        .supervise({ mode: 'managed', handshakeTimeoutMs: 20 })
        .catch(error => error)
      const closed = once(nativeChild!, 'close')
      await once(nativeChild!.stderr!, 'data')
      await vi.advanceTimersByTimeAsync(20)
      expect(await pending).toMatchObject({
        code: 'RUNTIME_HANDSHAKE_TIMEOUT',
        details: { processExited: true },
      })
      await closed
      expect(client.hasActiveSessions).toBe(false)
    } finally {
      if (nativeChild && nativeChild.exitCode === null && nativeChild.signalCode === null) {
        const closed = once(nativeChild, 'close')
        nativeChild.kill('SIGKILL')
        await closed
      }
    }

    const privateClient = createClient()
    const privateChild = mockSpawn()
    const privateRun = privateClient.run(['version', '--private', 'private-argument'])
    privateChild.stderr.feed('private-stderr')
    privateChild.stdout.feed(
      fixture('version.ndjson')
        .trim()
        .split('\n')
        .map(raw => {
          const event = JSON.parse(raw)
          return line(event.type === 'progress' ? { ...event, message: 'private-stdout' } : event)
        })
        .join('')
    )
    privateChild.close(0)
    expect(await privateRun).toMatchObject({ success: true })
    const diagnostics = loggerMock.info.mock.calls
      .map(([message]) => String(message))
      .filter(message => message.startsWith('[Runtime进程] '))
      .join('\n')
    expect(diagnostics).not.toBe('')
    for (const secret of [
      'private diagnostic',
      'private-argument',
      'private-stderr',
      'private-stdout',
      APP_ROOT,
      RUNTIME_PATH,
    ]) {
      expect(diagnostics).not.toContain(JSON.stringify(secret).slice(1, -1))
    }
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
      const work = client.run(['bootstrap'], { onStarted: () => started() }).catch(error => error)
      const closed = once(child!, 'close')
      try {
        await ready
        await client.stop(200)
        await closed
        const outcome = await work
        expect(client.hasActiveSessions).toBe(false)
        expect(child!.exitCode !== null || child!.signalCode !== null).toBe(true)
        if (behavior === 'finish-commit') {
          expect(outcome).toMatchObject({
            success: true,
            code: 'OK',
            exitCode: 0,
            result: { stage: 'bootstrap', status: 'ready_to_start' },
          })
          expect(child!.killed).toBe(false)
        } else {
          expect(outcome).toMatchObject({
            code: 'RUNTIME_EXITED_UNEXPECTEDLY',
            details: { command: 'bootstrap', processExited: true },
          })
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

// ==================== run ====================

describe('RuntimeClient.run', () => {
  it('握手后的坏行只记录并回调，不 kill 在途命令', async () => {
    const [helloLine, progressLine, resultLine] = fixture('version.ndjson').trim().split('\n')
    for (const invalidLine of [
      '{"protocol":1,\n',
      line({ ...JSON.parse(helloLine), protocol: 2 }),
    ]) {
      const client = createClient()
      const child = mockSpawn()
      const onStarted = vi.fn()
      const onProtocolError = vi.fn()
      const pending = client.run(['version'], { onStarted, onProtocolError })
      child.stdout.feed(invalidLine)
      const malformed = invalidLine.startsWith('{"protocol":1,')
      await expect(pending).rejects.toMatchObject({
        code: malformed ? 'RUNTIME_PROTOCOL_ERROR' : 'RUNTIME_PROTOCOL_MISMATCH',
        retryable: false,
        details: malformed
          ? { line: '{"protocol":1,', processExited: true }
          : { actualProtocol: 2, expectedProtocol: 1, processExited: true },
      })
      expect(onStarted).not.toHaveBeenCalled()
      expect(onProtocolError).toHaveBeenCalledTimes(malformed ? 1 : 0)
      expect(child.killed).toBe(true)
      expect(client.hasActiveSessions).toBe(false)
    }

    const client = createClient()
    const child = mockSpawn()
    const protocolErrors: RuntimeClientError[] = []
    const onStarted = vi.fn()

    const pending = client.run(['version'], {
      onStarted,
      onProtocolError: error => protocolErrors.push(error),
    })
    child.stdout.feed(`${helloLine}\n{"protocol":1,\n${progressLine}\n`)
    await Promise.resolve()

    expect(protocolErrors).toHaveLength(1)
    expect(protocolErrors[0]).toMatchObject({
      code: 'RUNTIME_PROTOCOL_ERROR',
      details: { line: '{"protocol":1,' },
    })
    expect(onStarted).toHaveBeenCalledTimes(1)
    expect(child.killed).toBe(false)

    child.stdout.feed(`${resultLine}\n`)
    child.close(0)
    const outcome = await pending

    expect(outcome.success).toBe(true)
    expect(outcome.protocolErrors).toHaveLength(1)
    expect(outcome.events.map(event => event.type)).toEqual(['hello', 'progress', 'result'])
    expect(child.killed).toBe(false)
    expect(client.hasActiveSessions).toBe(false)
  })
})
