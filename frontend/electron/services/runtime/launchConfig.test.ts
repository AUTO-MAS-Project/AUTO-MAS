import * as fs from 'fs'
import * as os from 'os'
import * as path from 'path'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import {
  RUNTIME_EXE_ENV,
  RUNTIME_MODE_ENV,
  isPersistedRuntimeLaunchMode,
  resolveRuntimeExecutable,
  resolveRuntimeLaunchConfig,
  resolveRuntimeLaunchMode,
  resolveRuntimeLaunchModeDetail,
} from './launchConfig'

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

vi.mock('electron', () => ({ app: { isPackaged: false } }))

// vi.mock 的 electron 桩是普通可变对象，isPackaged 直接在测试间改写它来切换构建默认值。
const { app: electronApp } = await import('electron')

function setPackaged(packaged: boolean): void {
  ;(electronApp as unknown as { isPackaged: boolean }).isPackaged = packaged
}

// 一定存在的可执行文件，用来代替尚未捆绑的 auto-mas-runtime.exe。
const EXISTING_EXE = process.execPath

/** 每个用例一个独立目录，避免真实文件系统读写互相污染。 */
let appRoot: string

function writePersistedLaunchMode(value: unknown): void {
  const configDir = path.join(appRoot, 'config')
  fs.mkdirSync(configDir, { recursive: true })
  fs.writeFileSync(
    path.join(configDir, 'frontend_config.json'),
    JSON.stringify({ Runtime: { LaunchMode: value } }),
    'utf8'
  )
}

beforeEach(() => {
  setPackaged(false)
  warn.mockClear()
  delete process.env[RUNTIME_MODE_ENV]
  delete process.env[RUNTIME_EXE_ENV]
  appRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'auto-mas-launch-config-'))
})

afterEach(() => {
  delete process.env[RUNTIME_MODE_ENV]
  delete process.env[RUNTIME_EXE_ENV]
  fs.rmSync(appRoot, { recursive: true, force: true })
})

describe('resolveRuntimeLaunchModeDetail：优先级矩阵', () => {
  it('三级都未设置时落到构建默认值（未打包 → off）', () => {
    expect(resolveRuntimeLaunchModeDetail(appRoot)).toEqual({ mode: 'off', source: 'default' })
  })

  it('环境变量覆盖持久化设置', () => {
    writePersistedLaunchMode('managed')
    process.env[RUNTIME_MODE_ENV] = 'development'

    expect(resolveRuntimeLaunchModeDetail(appRoot)).toEqual({
      mode: 'development',
      source: 'env',
    })
    expect(warn).not.toHaveBeenCalled()
  })

  it('未设环境变量时持久化设置覆盖构建默认值', () => {
    writePersistedLaunchMode('managed')
    setPackaged(false) // 构建默认值本应是 off，验证确实是设置项在生效

    expect(resolveRuntimeLaunchModeDetail(appRoot)).toEqual({ mode: 'managed', source: 'setting' })
  })

  it('持久化设置为 auto 时落到构建默认值', () => {
    writePersistedLaunchMode('auto')
    setPackaged(true)
    process.env[RUNTIME_EXE_ENV] = EXISTING_EXE

    expect(resolveRuntimeLaunchModeDetail(appRoot)).toEqual({ mode: 'managed', source: 'default' })
  })

  it('环境变量非法值 warn 后按持久化设置处理', () => {
    writePersistedLaunchMode('development')
    process.env[RUNTIME_MODE_ENV] = 'supervised'

    expect(resolveRuntimeLaunchModeDetail(appRoot)).toEqual({
      mode: 'development',
      source: 'setting',
    })
    expect(warn).toHaveBeenCalledOnce()
    expect(String(warn.mock.calls[0][0])).toContain('supervised')
  })

  it('持久化设置非法值 warn 后按构建默认值处理', () => {
    writePersistedLaunchMode('supervised')
    setPackaged(true)
    process.env[RUNTIME_EXE_ENV] = EXISTING_EXE

    expect(resolveRuntimeLaunchModeDetail(appRoot)).toEqual({ mode: 'managed', source: 'default' })
    expect(warn).toHaveBeenCalledOnce()
    expect(String(warn.mock.calls[0][0])).toContain('supervised')
  })

  it('环境变量与持久化设置都非法时，两级各 warn 一次后落到构建默认值', () => {
    writePersistedLaunchMode('nonsense')
    process.env[RUNTIME_MODE_ENV] = 'nonsense'

    expect(resolveRuntimeLaunchModeDetail(appRoot)).toEqual({ mode: 'off', source: 'default' })
    expect(warn).toHaveBeenCalledTimes(2)
  })

  it('持久化设置文件不存在时直接落到构建默认值，不记 warning', () => {
    expect(resolveRuntimeLaunchModeDetail(appRoot)).toEqual({ mode: 'off', source: 'default' })
    expect(warn).not.toHaveBeenCalled()
  })

  it('持久化设置文件 JSON 损坏时记 warning 并落到构建默认值', () => {
    const configDir = path.join(appRoot, 'config')
    fs.mkdirSync(configDir, { recursive: true })
    fs.writeFileSync(path.join(configDir, 'frontend_config.json'), '{not json', 'utf8')

    expect(resolveRuntimeLaunchModeDetail(appRoot)).toEqual({ mode: 'off', source: 'default' })
    expect(warn).toHaveBeenCalledOnce()
  })

  it('空串环境变量按未设置处理，不记 warning，落到持久化设置', () => {
    writePersistedLaunchMode('managed')
    process.env[RUNTIME_MODE_ENV] = '   '

    expect(resolveRuntimeLaunchModeDetail(appRoot)).toEqual({ mode: 'managed', source: 'setting' })
    expect(warn).not.toHaveBeenCalled()
  })

  it('三个合法环境变量取值都能解析，大小写与空白不敏感', () => {
    process.env[RUNTIME_MODE_ENV] = 'off'
    expect(resolveRuntimeLaunchMode(appRoot)).toBe('off')

    process.env[RUNTIME_MODE_ENV] = ' development '
    expect(resolveRuntimeLaunchMode(appRoot)).toBe('development')

    process.env[RUNTIME_MODE_ENV] = 'MANAGED'
    expect(resolveRuntimeLaunchMode(appRoot)).toBe('managed')

    expect(warn).not.toHaveBeenCalled()
  })
})

describe('resolveRuntimeLaunchModeDetail：构建默认值的四种组合', () => {
  it('打包 + 已捆绑 Runtime → managed', () => {
    setPackaged(true)
    process.env[RUNTIME_EXE_ENV] = EXISTING_EXE

    expect(resolveRuntimeLaunchModeDetail(appRoot)).toEqual({ mode: 'managed', source: 'default' })
  })

  it('打包 + 未捆绑 Runtime → off', () => {
    setPackaged(true)

    expect(resolveRuntimeLaunchModeDetail(appRoot)).toEqual({ mode: 'off', source: 'default' })
  })

  it('未打包 + 已捆绑 Runtime → off（源码开发默认仍走旧链路）', () => {
    setPackaged(false)
    process.env[RUNTIME_EXE_ENV] = EXISTING_EXE

    expect(resolveRuntimeLaunchModeDetail(appRoot)).toEqual({ mode: 'off', source: 'default' })
  })

  it('未打包 + 未捆绑 Runtime → off', () => {
    setPackaged(false)

    expect(resolveRuntimeLaunchModeDetail(appRoot)).toEqual({ mode: 'off', source: 'default' })
  })
})

describe('isPersistedRuntimeLaunchMode', () => {
  it('接受 auto/off/development/managed，拒绝其它取值与非字符串', () => {
    expect(isPersistedRuntimeLaunchMode('auto')).toBe(true)
    expect(isPersistedRuntimeLaunchMode('off')).toBe(true)
    expect(isPersistedRuntimeLaunchMode('development')).toBe(true)
    expect(isPersistedRuntimeLaunchMode('managed')).toBe(true)
    expect(isPersistedRuntimeLaunchMode('supervised')).toBe(false)
    expect(isPersistedRuntimeLaunchMode(undefined)).toBe(false)
    expect(isPersistedRuntimeLaunchMode(123)).toBe(false)
  })
})

describe('持久化设置读写往返', () => {
  it('set 写入的形状能被 resolveRuntimeLaunchModeDetail 读回（模拟 main.ts 的 loadConfig/saveConfig）', () => {
    // main.ts 的 saveConfig 是整份 AppConfig 回写，这里只关心 Runtime 节点，其余字段不影响解析。
    const wholeConfig = {
      UI: { IfShowTray: false },
      Start: { IfSelfStart: false },
      Update: { IfAutoUpdate: false },
      Function: { IfEnableTelemetry: true },
      Runtime: { LaunchMode: 'development' },
    }
    const configDir = path.join(appRoot, 'config')
    fs.mkdirSync(configDir, { recursive: true })
    fs.writeFileSync(
      path.join(configDir, 'frontend_config.json'),
      JSON.stringify(wholeConfig, null, 2),
      'utf8'
    )

    expect(resolveRuntimeLaunchModeDetail(appRoot)).toEqual({
      mode: 'development',
      source: 'setting',
    })
  })
})

describe('resolveRuntimeExecutable', () => {
  it('环境变量指向的文件存在时直接使用', () => {
    process.env[RUNTIME_EXE_ENV] = EXISTING_EXE

    expect(resolveRuntimeExecutable()).toBe(EXISTING_EXE)
  })

  it('环境变量指向的文件不存在时记 warning，并因未捆绑而返回 null', () => {
    process.env[RUNTIME_EXE_ENV] = 'D:\\nowhere\\auto-mas-runtime.exe'

    expect(resolveRuntimeExecutable()).toBeNull()
    expect(warn).toHaveBeenCalledOnce()
  })

  it('未指定且安装包未捆绑时返回 null', () => {
    expect(resolveRuntimeExecutable()).toBeNull()
  })
})

describe('resolveRuntimeLaunchConfig', () => {
  it('off 模式不去定位可执行文件', () => {
    process.env[RUNTIME_EXE_ENV] = EXISTING_EXE

    expect(resolveRuntimeLaunchConfig(appRoot)).toEqual({
      mode: 'off',
      runtimePath: null,
      appRoot,
    })
  })

  it('development 模式把当前 appRoot 作为 --repo', () => {
    process.env[RUNTIME_MODE_ENV] = 'development'
    process.env[RUNTIME_EXE_ENV] = EXISTING_EXE

    expect(resolveRuntimeLaunchConfig(appRoot)).toEqual({
      mode: 'development',
      runtimePath: EXISTING_EXE,
      appRoot,
      repo: appRoot,
    })
  })

  it('managed 模式不传 --repo', () => {
    process.env[RUNTIME_MODE_ENV] = 'managed'
    process.env[RUNTIME_EXE_ENV] = EXISTING_EXE

    expect(resolveRuntimeLaunchConfig(appRoot)).toEqual({
      mode: 'managed',
      runtimePath: EXISTING_EXE,
      appRoot,
      repo: undefined,
    })
  })

  it('持久化设置也能驱动 resolveRuntimeLaunchConfig（不只是环境变量）', () => {
    writePersistedLaunchMode('managed')
    process.env[RUNTIME_EXE_ENV] = EXISTING_EXE

    expect(resolveRuntimeLaunchConfig(appRoot)).toEqual({
      mode: 'managed',
      runtimePath: EXISTING_EXE,
      appRoot,
      repo: undefined,
    })
  })
})
