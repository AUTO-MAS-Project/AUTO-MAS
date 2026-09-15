import * as fs from 'fs'
import * as os from 'os'
import * as path from 'path'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const appRootRef = { value: '' }
vi.mock('electron', () => ({ app: { getAppPath: () => '/tmp/app', getPath: () => appRootRef.value } }))
vi.mock('./instanceConfig', () => ({
  isDevelopmentEnvironment: () => false,
}))

import { GitInstaller } from './environmentService'

// 复现“Git 安装中断留下残缺目录，旧版直接判失败、只能手删 environment”的现场。
describe('GitInstaller 残缺安装自愈', () => {
  let appRoot: string
  beforeEach(() => {
    appRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'mas-gitfix-'))
    appRootRef.value = appRoot
  })
  afterEach(() => {
    fs.rmSync(appRoot, { recursive: true, force: true })
  })

  it('git.exe 存在但不可运行时清理残缺目录，按缺失处理以触发重装', async () => {
    const gitPath = path.join(appRoot, 'environment', 'git')
    const binDir = path.join(gitPath, 'bin')
    fs.mkdirSync(binDir, { recursive: true })
    // 残缺安装：git.exe 存在，但它不是可执行文件（跑不起来）
    fs.writeFileSync(path.join(binDir, 'git.exe'), 'not a real exe')

    const installer = new GitInstaller(appRoot, { getMirrors: () => [] } as never)
    const check = await (installer as unknown as {
      checkEnvironment: () => Promise<{ exeExists: boolean; canRun: boolean }>
    }).checkEnvironment()

    // 关键：不再是旧的 { exeExists: true, canRun: false }（那会让安装流程直接放弃）
    expect(check).toMatchObject({ exeExists: false, canRun: false })
    expect(fs.existsSync(gitPath)).toBe(false)
  })
})