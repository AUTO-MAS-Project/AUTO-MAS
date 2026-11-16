import * as fs from 'fs'
import * as os from 'os'
import * as path from 'path'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vite-plus/test'

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
  delete process.env[RUNTIME_MODE_ENV]
  delete process.env[RUNTIME_EXE_ENV]
  fs.rmSync(appRoot, { recursive: true, force: true })
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
