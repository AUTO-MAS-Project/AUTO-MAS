import { spawn } from 'child_process'
import { EventEmitter } from 'node:events'
import * as fs from 'fs'
import * as os from 'os'
import * as path from 'path'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { RuntimeClient } from './client'
import { createRuntimeClient } from './runtimeClientFactory'

vi.mock('child_process', () => ({ spawn: vi.fn() }))
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

// ==================== 假子进程（只需要能收一条 hello 完成握手，不关心后续） ====================

class FakeReadable extends EventEmitter {
  setEncoding(): this {
    return this
  }

  feed(text: string): void {
    this.emit('data', text)
  }
}

class FakeWritable extends EventEmitter {
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

  kill(): boolean {
    this.killed = true
    return true
  }
}

const spawnMock = vi.mocked(spawn)
const RUNTIME_PATH = process.execPath

function spawnedEnv(): NodeJS.ProcessEnv {
  return (spawnMock.mock.calls[0][2] as { env: NodeJS.ProcessEnv }).env
}

/** 喂一条最小 hello 事件，让 run() 的握手立刻完成，避免留下 10s 的悬空握手计时器。 */
function feedHello(): void {
  const child = spawnMock.mock.results[0].value as FakeChild
  const hello = {
    protocol: 1,
    operationId: '01M1F6M33JFZZ7Y85BE5S849ZN',
    timestamp: '2026-09-01T21:20:03.442+02:00',
    type: 'hello',
    sequence: 1,
    runtimeVersion: 'dev',
    command: 'doctor',
    capabilities: [],
  }
  child.stdout.feed(`${JSON.stringify(hello)}\n`)
}

let appRoot: string

function writeBackendConfig(value: unknown): void {
  const configDir = path.join(appRoot, 'config')
  fs.mkdirSync(configDir, { recursive: true })
  fs.writeFileSync(path.join(configDir, 'Config.json'), JSON.stringify(value), 'utf8')
}

beforeEach(() => {
  spawnMock.mockReset()
  spawnMock.mockReturnValue(new FakeChild() as never)
  // 宿主环境若带着这个变量，会经 process.env 原样继承，干扰下面对「不设」的断言。
  delete process.env.AUTO_MAS_ENV
  appRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'auto-mas-runtime-factory-'))
})

afterEach(() => {
  fs.rmSync(appRoot, { recursive: true, force: true })
})

describe('createRuntimeClient', () => {
  it('返回 RuntimeClient 实例', () => {
    const client = createRuntimeClient({ runtimePath: RUNTIME_PATH, appRoot })
    expect(client).toBeInstanceOf(RuntimeClient)
  })

  it('关闭遥测时，spawn 出的 Runtime 子进程环境带 AUTO_MAS_TELEMETRY=disabled', () => {
    writeBackendConfig({ Function: { IfEnableTelemetry: false } })

    void createRuntimeClient({ runtimePath: RUNTIME_PATH, appRoot })
      .run(['doctor'])
      .catch(() => undefined)
    feedHello()

    expect(spawnedEnv().AUTO_MAS_TELEMETRY).toBe('disabled')
  })

  it('开启遥测时，不设 AUTO_MAS_TELEMETRY', () => {
    writeBackendConfig({ Function: { IfEnableTelemetry: true } })

    void createRuntimeClient({ runtimePath: RUNTIME_PATH, appRoot })
      .run(['doctor'])
      .catch(() => undefined)
    feedHello()

    expect(spawnedEnv().AUTO_MAS_TELEMETRY).toBeUndefined()
  })

  it('调用方显式传入的 env 优先于遥测开关注入的默认值', () => {
    writeBackendConfig({ Function: { IfEnableTelemetry: false } })

    void createRuntimeClient({
      runtimePath: RUNTIME_PATH,
      appRoot,
      env: { AUTO_MAS_TELEMETRY: undefined },
    })
      .run(['doctor'])
      .catch(() => undefined)
    feedHello()

    expect(spawnedEnv().AUTO_MAS_TELEMETRY).toBeUndefined()
  })

  it('遥测开关从 dataRoot 读，而不是从 --app-root 读', () => {
    // development 模式：--app-root 是仓外的 Runtime 根目录，Config.json 在源码根（dataRoot）。
    writeBackendConfig({ Function: { IfEnableTelemetry: false } })
    const runtimeRoot = path.join(appRoot, 'runtime-root-without-config')
    fs.mkdirSync(runtimeRoot, { recursive: true })

    void createRuntimeClient({ runtimePath: RUNTIME_PATH, appRoot: runtimeRoot, dataRoot: appRoot })
      .run(['doctor'])
      .catch(() => undefined)
    feedHello()

    expect(spawnedEnv().AUTO_MAS_TELEMETRY).toBe('disabled')
    // --app-root 仍是 Runtime 根目录，dataRoot 不会漏进参数。
    expect(spawnMock.mock.calls[0][1]).toEqual(expect.arrayContaining(['--app-root', runtimeRoot]))
    expect(spawnMock.mock.calls[0][1]).not.toContain(appRoot)
  })

  it('development 模式给 Runtime 子进程带上 AUTO_MAS_ENV=development', () => {
    void createRuntimeClient({ runtimePath: RUNTIME_PATH, appRoot, launchMode: 'development' })
      .run(['doctor'])
      .catch(() => undefined)
    feedHello()

    expect(spawnedEnv().AUTO_MAS_ENV).toBe('development')
  })

  it('managed 模式不设 AUTO_MAS_ENV', () => {
    void createRuntimeClient({ runtimePath: RUNTIME_PATH, appRoot, launchMode: 'managed' })
      .run(['doctor'])
      .catch(() => undefined)
    feedHello()

    expect(spawnedEnv().AUTO_MAS_ENV).toBeUndefined()
  })
})
