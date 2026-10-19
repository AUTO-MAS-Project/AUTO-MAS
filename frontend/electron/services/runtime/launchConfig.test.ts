import * as fs from 'fs'
import * as os from 'os'
import * as path from 'path'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vite-plus/test'

import {
  RUNTIME_BACKUP_SUFFIX,
  RUNTIME_EXECUTABLE_NAME,
  RUNTIME_EXE_ENV,
  RUNTIME_MODE_ENV,
  resolveDevelopmentRuntimeRoot,
  resolveRuntimeExecutable,
  resolveRuntimeLaunchConfig,
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

describe('resolveRuntimeExecutable', () => {
  it('环境变量指向的文件存在时直接使用', () => {
    process.env[RUNTIME_EXE_ENV] = EXISTING_EXE

    expect(resolveRuntimeExecutable()).toBe(EXISTING_EXE)
  })

  describe('捆绑位置', () => {
    /** 非 Electron 环境没有 resourcesPath，用例自己指一个临时目录。 */
    let resourcesPath: string | undefined
    const processWithResources = process as NodeJS.Process & { resourcesPath?: string }

    beforeEach(() => {
      resourcesPath = processWithResources.resourcesPath
      processWithResources.resourcesPath = path.join(appRoot, 'resources')
      fs.mkdirSync(processWithResources.resourcesPath, { recursive: true })
    })

    afterEach(() => {
      if (resourcesPath === undefined) {
        delete processWithResources.resourcesPath
      } else {
        processWithResources.resourcesPath = resourcesPath
      }
    })

    it('exe 缺失但上次更新 Runtime 留下的备份还在时，先把备份改回来再用', () => {
      const bundled = path.join(appRoot, 'resources', RUNTIME_EXECUTABLE_NAME)
      fs.writeFileSync(`${bundled}${RUNTIME_BACKUP_SUFFIX}`, 'previous', 'utf8')

      expect(resolveRuntimeExecutable()).toBe(bundled)
      expect(fs.readFileSync(bundled, 'utf8')).toBe('previous')
      expect(fs.existsSync(`${bundled}${RUNTIME_BACKUP_SUFFIX}`)).toBe(false)
      expect(warn).toHaveBeenCalledOnce()
    })
  })
})

describe('resolveRuntimeLaunchConfig', () => {
  it('development 模式把传入的源码根作为 --repo 与 dataRoot，--app-root 另取仓外目录', () => {
    process.env[RUNTIME_MODE_ENV] = 'development'
    process.env[RUNTIME_EXE_ENV] = EXISTING_EXE

    const config = resolveRuntimeLaunchConfig(appRoot)
    expect(config).toEqual({
      mode: 'development',
      runtimePath: EXISTING_EXE,
      appRoot: resolveDevelopmentRuntimeRoot(appRoot),
      repo: appRoot,
      dataRoot: appRoot,
    })
    // Runtime 拒绝 runtime_root_inside_development_repo：Runtime 根既不能等于源码根，也不能在它里面。
    expect(config.appRoot).not.toBe(appRoot)
    expect(config.appRoot.startsWith(appRoot + path.sep)).toBe(false)
  })

  it('managed 模式不传 --repo，--app-root 就是用户数据根', () => {
    process.env[RUNTIME_MODE_ENV] = 'managed'
    process.env[RUNTIME_EXE_ENV] = EXISTING_EXE

    expect(resolveRuntimeLaunchConfig(appRoot)).toEqual({
      mode: 'managed',
      runtimePath: EXISTING_EXE,
      appRoot,
      repo: undefined,
      dataRoot: appRoot,
    })
  })
})
