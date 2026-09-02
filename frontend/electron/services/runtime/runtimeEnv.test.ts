import * as fs from 'fs'
import * as os from 'os'
import * as path from 'path'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { RUNTIME_APP_ENV, RUNTIME_TELEMETRY_ENV, buildRuntimeEnv } from './runtimeEnv'

const warn = vi.fn()

vi.mock('../logger', () => ({
  getLogger: () => ({
    error: vi.fn(),
    warn: (...args: unknown[]) => warn(...args),
    info: vi.fn(),
    verbose: vi.fn(),
    debug: vi.fn(),
    silly: vi.fn(),
  }),
}))

let appRoot: string

function writeBackendConfig(value: unknown): void {
  const configDir = path.join(appRoot, 'config')
  fs.mkdirSync(configDir, { recursive: true })
  fs.writeFileSync(path.join(configDir, 'Config.json'), JSON.stringify(value), 'utf8')
}

beforeEach(() => {
  warn.mockClear()
  appRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'auto-mas-runtime-env-'))
})

afterEach(() => {
  fs.rmSync(appRoot, { recursive: true, force: true })
})

describe('buildRuntimeEnv', () => {
  it('Config.json 不存在时按开启处理，不设 AUTO_MAS_TELEMETRY', () => {
    expect(buildRuntimeEnv(appRoot)).toEqual({})
    expect(warn).not.toHaveBeenCalled()
  })

  it('IfEnableTelemetry 缺失时按开启处理', () => {
    writeBackendConfig({ Function: {} })

    expect(buildRuntimeEnv(appRoot)).toEqual({})
  })

  it('IfEnableTelemetry 为 true 时按开启处理', () => {
    writeBackendConfig({ Function: { IfEnableTelemetry: true } })

    expect(buildRuntimeEnv(appRoot)).toEqual({})
  })

  it('IfEnableTelemetry 为 false 时透传 AUTO_MAS_TELEMETRY=disabled', () => {
    writeBackendConfig({ Function: { IfEnableTelemetry: false } })

    expect(buildRuntimeEnv(appRoot)).toEqual({ [RUNTIME_TELEMETRY_ENV]: 'disabled' })
  })

  it('结果里不含任何 offline 相关的键——遥测与联网开关是两回事', () => {
    writeBackendConfig({ Function: { IfEnableTelemetry: false } })

    const env = buildRuntimeEnv(appRoot)
    expect(Object.keys(env)).toEqual([RUNTIME_TELEMETRY_ENV])
    expect(env).not.toHaveProperty('offline')
    expect(env).not.toHaveProperty('--offline')
  })

  it('Config.json 损坏时记 warning 并按开启处理', () => {
    const configDir = path.join(appRoot, 'config')
    fs.mkdirSync(configDir, { recursive: true })
    fs.writeFileSync(path.join(configDir, 'Config.json'), '{not json', 'utf8')

    expect(buildRuntimeEnv(appRoot)).toEqual({})
    expect(warn).toHaveBeenCalledOnce()
  })
})

describe('buildRuntimeEnv：开发标记', () => {
  it('development 模式追加 AUTO_MAS_ENV=development', () => {
    expect(buildRuntimeEnv(appRoot, 'development')).toEqual({ [RUNTIME_APP_ENV]: 'development' })
  })

  it('development 模式且关闭遥测时两项同时透传', () => {
    writeBackendConfig({ Function: { IfEnableTelemetry: false } })

    expect(buildRuntimeEnv(appRoot, 'development')).toEqual({
      [RUNTIME_TELEMETRY_ENV]: 'disabled',
      [RUNTIME_APP_ENV]: 'development',
    })
  })

  it('managed / off / 未指定模式都不碰 AUTO_MAS_ENV', () => {
    expect(buildRuntimeEnv(appRoot, 'managed')).toEqual({})
    expect(buildRuntimeEnv(appRoot, 'off')).toEqual({})
    expect(buildRuntimeEnv(appRoot)).toEqual({})
  })
})
