import * as fs from 'fs'
import * as os from 'os'
import * as path from 'path'
import { spawn, spawnSync, execFile } from 'child_process'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { RepositoryService } from './repositoryService'

/**
 * 真实 git 集成测试：用 junction 把 environment/git 指向本机 git 安装，
 * 在真实文件系统上驱动 RepositoryService，覆盖“残留 git 进程占住 repo 导致删不掉”的现场。
 *
 * 依赖本机可用的 git 安装；没有时整体跳过，不阻塞其他环境的测试。
 */
const GIT_INSTALL = process.env.MAS_TEST_GIT_INSTALL ?? 'D:\\Git'
const hasLocalGit = fs.existsSync(path.join(GIT_INSTALL, 'bin', 'git.exe'))

function git(args: string[], cwd?: string) {
  return spawnSync('git', args, { cwd, stdio: 'pipe', encoding: 'utf8', windowsHide: true })
}
const sleep = (ms: number) => new Promise(r => setTimeout(r, ms))
const alive = (pid: number) => {
  try {
    process.kill(pid, 0)
    return true
  } catch {
    return false
  }
}

describe.skipIf(!hasLocalGit)('RepositoryService 真实 git 集成', () => {
  let appRoot: string
  let junction: string
  let lockPid = 0
  const mirrorService = { getMirrors: () => [] as unknown[] }

  beforeEach(() => {
    appRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'mas-realrepo-'))
    const seed = path.join(appRoot, 'seed')
    fs.mkdirSync(seed, { recursive: true })
    git(['init', '-b', 'dev', seed])
    fs.mkdirSync(path.join(seed, 'app'), { recursive: true })
    fs.writeFileSync(path.join(seed, 'app', 'route.py'), 'x = 1\n')
    fs.writeFileSync(path.join(seed, 'main.py'), 'print(1)\n')
    git(['-C', seed, '-c', 'user.email=a@a.a', '-c', 'user.name=a', 'add', '.'])
    git(['-C', seed, '-c', 'user.email=a@a.a', '-c', 'user.name=a', 'commit', '-m', 'init'])
    const bare = path.join(appRoot, 'src.git')
    git(['clone', '--bare', seed, bare])
    junction = path.join(appRoot, 'environment')
    fs.mkdirSync(junction, { recursive: true })
    spawnSync('cmd', ['/c', 'mklink', '/J', path.join(junction, 'git'), GIT_INSTALL], {
      stdio: 'pipe',
      windowsHide: true,
    })
    mirrorService.getMirrors = () => [{ key: 'local', name: 'local', url: bare, type: 'mirror' }]
  }, 30000)

  afterEach(async () => {
    if (lockPid && alive(lockPid)) {
      await new Promise(res => execFile('taskkill', ['/pid', String(lockPid), '/t', '/f'], () => res()))
    }
    lockPid = 0
    // 只删 junction 本身，绝不递归进入真实 git 安装目录
    try {
      fs.rmSync(path.join(junction, 'git'), { recursive: false, force: true })
    } catch {
      // junction 可能已被其他清理步骤移除，忽略
    }
    fs.rmSync(appRoot, { recursive: true, force: true })
  }, 30000)

  it('真实 clone 成功并把工作树部署到根目录', async () => {
    const service = new RepositoryService(appRoot, mirrorService as never, 'dev')
    const result = await service.pullRepository()
    expect(result.success, { message: result.error }).toBe(true)
    expect(fs.readFileSync(path.join(appRoot, 'repo', '.git', 'HEAD'), 'utf8')).toContain('dev')
    expect(fs.existsSync(path.join(appRoot, 'main.py'))).toBe(true)
    expect(fs.existsSync(path.join(appRoot, 'app', 'route.py'))).toBe(true)
    expect(fs.existsSync(path.join(appRoot, '.git'))).toBe(true)
  }, 60000)

  it('残留 git 进程占住 repo 时，服务清理孤儿并完成重新 clone', async () => {
    const repo = path.join(appRoot, 'repo')
    const gitDir = path.join(repo, '.git')
    fs.mkdirSync(gitDir, { recursive: true })
    fs.writeFileSync(path.join(gitDir, 'broken'), 'x')

    // 用自带 git（junction 路径）起长驻进程，cwd 停在 repo 内，复刻残留孤儿
    const bundledGit = path.join(junction, 'git', 'bin', 'git.exe')
    const holder = spawn(bundledGit, ['hash-object', '--stdin'], {
      cwd: repo,
      detached: true,
      stdio: ['pipe', 'ignore', 'ignore'],
      windowsHide: true,
    })
    holder.unref()
    lockPid = holder.pid as number
    await sleep(800)
    expect(alive(lockPid)).toBe(true)

    // 先确认这确实是旧逻辑删不掉的状态
    let before = 'OK'
    try {
      fs.rmSync(repo, { recursive: true, force: true })
    } catch (e) {
      before = (e as NodeJS.ErrnoException).code as string
    }
    expect(before).toBe('EPERM')

    const service = new RepositoryService(appRoot, mirrorService as never, 'dev')
    const result = await service.pullRepository()
    expect(result.success, { message: result.error }).toBe(true)
    expect(fs.existsSync(path.join(repo, '.git', 'HEAD'))).toBe(true)
  }, 60000)
})