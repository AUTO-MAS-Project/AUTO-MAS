import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import {
  RUNTIME_EXE_ENV,
  RUNTIME_MODE_ENV,
  resolveRuntimeExecutable,
  resolveRuntimeLaunchConfig,
  resolveRuntimeLaunchMode,
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

const APP_ROOT = 'D:\\AUTO-MAS'
// 一定存在的可执行文件，用来代替尚未捆绑的 auto-mas-runtime.exe。
const EXISTING_EXE = process.execPath

beforeEach(() => {
  warn.mockClear()
  delete process.env[RUNTIME_MODE_ENV]
  delete process.env[RUNTIME_EXE_ENV]
})

afterEach(() => {
  delete process.env[RUNTIME_MODE_ENV]
  delete process.env[RUNTIME_EXE_ENV]
})

describe('resolveRuntimeLaunchMode', () => {
  it('未设置环境变量时默认关闭', () => {
    expect(resolveRuntimeLaunchMode()).toBe('off')
  })

  it('三个合法取值都能解析，大小写与空白不敏感', () => {
    process.env[RUNTIME_MODE_ENV] = 'off'
    expect(resolveRuntimeLaunchMode()).toBe('off')

    process.env[RUNTIME_MODE_ENV] = ' development '
    expect(resolveRuntimeLaunchMode()).toBe('development')

    process.env[RUNTIME_MODE_ENV] = 'MANAGED'
    expect(resolveRuntimeLaunchMode()).toBe('managed')

    expect(warn).not.toHaveBeenCalled()
  })

  it('非法取值记 warning 并回落到 off', () => {
    process.env[RUNTIME_MODE_ENV] = 'supervised'

    expect(resolveRuntimeLaunchMode()).toBe('off')
    expect(warn).toHaveBeenCalledOnce()
    expect(String(warn.mock.calls[0][0])).toContain('supervised')
  })

  it('空串按未设置处理，不记 warning', () => {
    process.env[RUNTIME_MODE_ENV] = '   '

    expect(resolveRuntimeLaunchMode()).toBe('off')
    expect(warn).not.toHaveBeenCalled()
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

    expect(resolveRuntimeLaunchConfig(APP_ROOT)).toEqual({
      mode: 'off',
      runtimePath: null,
      appRoot: APP_ROOT,
    })
  })

  it('development 模式把当前 appRoot 作为 --repo', () => {
    process.env[RUNTIME_MODE_ENV] = 'development'
    process.env[RUNTIME_EXE_ENV] = EXISTING_EXE

    expect(resolveRuntimeLaunchConfig(APP_ROOT)).toEqual({
      mode: 'development',
      runtimePath: EXISTING_EXE,
      appRoot: APP_ROOT,
      repo: APP_ROOT,
    })
  })

  it('managed 模式不传 --repo', () => {
    process.env[RUNTIME_MODE_ENV] = 'managed'
    process.env[RUNTIME_EXE_ENV] = EXISTING_EXE

    expect(resolveRuntimeLaunchConfig(APP_ROOT)).toEqual({
      mode: 'managed',
      runtimePath: EXISTING_EXE,
      appRoot: APP_ROOT,
      repo: undefined,
    })
  })
})
