import * as fs from 'fs'
import * as os from 'os'
import * as path from 'path'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vite-plus/test'
import { app } from 'electron'
import { getApplicationEnvironment, getDevelopmentServerUrl } from '../instanceConfig'
import { getAppRoot } from '../environmentService'

import {
  RUNTIME_BACKUP_SUFFIX,
  RUNTIME_EXECUTABLE_NAME,
  RUNTIME_EXE_ENV,
  RUNTIME_MODE_ENV,
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

/** 每个用例一个独立目录，避免真实文件系统读写互相污染。 */
let appRoot: string

beforeEach(() => {
  warn.mockClear()
  delete process.env[RUNTIME_MODE_ENV]
  delete process.env[RUNTIME_EXE_ENV]
  appRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'auto-mas-launch-config-'))
})

afterEach(() => {
  delete process.env.AUTO_MAS_BACKEND_REPO
  delete process.env.AUTO_MAS_BACKEND_RUNTIME_ROOT
  delete process.env.VITE_DEV_SERVER_URL
  Object.defineProperty(app, 'isPackaged', { value: false, configurable: true })
  Reflect.deleteProperty(app, 'getPath')
  delete process.env[RUNTIME_MODE_ENV]
  delete process.env[RUNTIME_EXE_ENV]
  fs.rmSync(appRoot, { recursive: true, force: true })
})

describe('安装版使用开发后端', () => {
  it('显式选择源码后隔离数据和应用环境，取消选择恢复正式模式', () => {
    Object.defineProperty(app, 'isPackaged', { value: true, configurable: true })
    const source = path.join(appRoot, 'source')
    const installed = path.join(appRoot, 'installed')
    Object.defineProperty(app, 'getPath', {
      value: () => path.join(installed, 'AUTO-MAS.exe'),
      configurable: true,
    })
    process.env.AUTO_MAS_BACKEND_REPO = source
    process.env[RUNTIME_MODE_ENV] = 'managed'
    process.env.VITE_DEV_SERVER_URL = 'http://127.0.0.1:5173'
    const config = resolveRuntimeLaunchConfig(installed)
    expect(config).toMatchObject({
      mode: 'development',
      repo: source,
      dataRoot: source,
      appRoot: installed,
      reuseManagedEnvironment: true,
    })
    expect(getAppRoot()).toBe(source)
    expect(getApplicationEnvironment()).toBe('development')
    // 安装包仍加载自己的页面，不因切换后端而加载外部页面。
    expect(getDevelopmentServerUrl()).toBeUndefined()
    delete process.env.AUTO_MAS_BACKEND_REPO
    expect(resolveRuntimeLaunchConfig(installed)).toMatchObject({
      mode: 'managed',
      dataRoot: installed,
    })
    expect(getApplicationEnvironment()).toBe('production')
  })
})

describe('resolveRuntimeExecutable', () => {
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

    // 恢复真实备份后，后端启动使用的配置也必须能重新定位它。
    it('exe 缺失但上次更新 Runtime 留下的备份还在时，先把备份改回来再用', () => {
      const bundled = path.join(appRoot, 'resources', RUNTIME_EXECUTABLE_NAME)
      fs.writeFileSync(`${bundled}${RUNTIME_BACKUP_SUFFIX}`, 'previous', 'utf8')
      expect(fs.existsSync(bundled)).toBe(false)

      expect(resolveRuntimeExecutable()).toBe(bundled)
      expect(resolveRuntimeLaunchConfig(appRoot).runtimePath).toBe(bundled)
      expect(fs.readFileSync(bundled, 'utf8')).toBe('previous')
      expect(fs.existsSync(`${bundled}${RUNTIME_BACKUP_SUFFIX}`)).toBe(false)
      expect(fs.readdirSync(path.dirname(bundled))).toEqual([RUNTIME_EXECUTABLE_NAME])
      expect(warn).toHaveBeenCalledOnce()
    })
  })
})
