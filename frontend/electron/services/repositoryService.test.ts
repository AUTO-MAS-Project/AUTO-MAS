import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { afterEach, describe, expect, it } from 'vitest'
import { RepositoryService } from './repositoryService'

/**
 * 部署替换的原子性：`replaceItem` 先整体复制到 `<目标>.new`，再改名换入。
 *
 * 原来的「先 rmSync 掉目标、再逐文件 copyFileSync」一旦中断就会留下残缺的 app/，
 * 后端下次启动直接 ModuleNotFoundError；这里用真实临时目录锁住「换入后内容完整、
 * 不留残留、失败不动目标」这三条语义。
 */

const roots: string[] = []

const makeRoot = (): string => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'mas-deploy-'))
  roots.push(root)
  return root
}

const makeService = (appRoot: string): RepositoryService =>
  new RepositoryService(appRoot, {} as never)

const callReplaceItem = (service: RepositoryService, src: string, dst: string): void => {
  const target = service as unknown as { replaceItem(s: string, d: string): void }
  target.replaceItem(src, dst)
}

afterEach(() => {
  for (const root of roots.splice(0)) {
    fs.rmSync(root, { recursive: true, force: true })
  }
})

describe('RepositoryService.replaceItem', () => {
  it('整目录替换后内容与源一致，且不留 .new / .old 残留', () => {
    const root = makeRoot()
    const repoPath = path.join(root, 'repo')
    const appRoot = path.join(root, 'app-root')
    fs.mkdirSync(path.join(repoPath, 'app', 'core'), { recursive: true })
    fs.writeFileSync(path.join(repoPath, 'app', 'core', 'timer.py'), 'new')
    fs.mkdirSync(path.join(appRoot, 'app'), { recursive: true })
    fs.writeFileSync(path.join(appRoot, 'app', 'stale.py'), 'old')

    callReplaceItem(makeService(appRoot), path.join(repoPath, 'app'), path.join(appRoot, 'app'))

    expect(fs.readFileSync(path.join(appRoot, 'app', 'core', 'timer.py'), 'utf8')).toBe('new')
    expect(fs.existsSync(path.join(appRoot, 'app', 'stale.py'))).toBe(false)
    expect(fs.existsSync(path.join(appRoot, 'app.new'))).toBe(false)
    expect(fs.existsSync(path.join(appRoot, 'app.old'))).toBe(false)
  })

  it('目标不存在时直接建出来', () => {
    const root = makeRoot()
    const repoPath = path.join(root, 'repo')
    const appRoot = path.join(root, 'app-root')
    fs.mkdirSync(repoPath, { recursive: true })
    fs.writeFileSync(path.join(repoPath, 'main.py'), 'print(1)')

    callReplaceItem(makeService(appRoot), path.join(repoPath, 'main.py'), path.join(appRoot, 'main.py'))

    expect(fs.readFileSync(path.join(appRoot, 'main.py'), 'utf8')).toBe('print(1)')
    expect(fs.existsSync(path.join(appRoot, 'main.py.new'))).toBe(false)
  })

  it('清掉上次中断留下的 .new / .old 残留', () => {
    const root = makeRoot()
    const repoPath = path.join(root, 'repo')
    const appRoot = path.join(root, 'app-root')
    fs.mkdirSync(path.join(repoPath, 'app'), { recursive: true })
    fs.writeFileSync(path.join(repoPath, 'app', 'fresh.py'), 'fresh')
    // 上一次部署中断的现场
    fs.mkdirSync(path.join(appRoot, 'app.new'), { recursive: true })
    fs.writeFileSync(path.join(appRoot, 'app.new', 'half.py'), 'half')
    fs.mkdirSync(path.join(appRoot, 'app.old'), { recursive: true })
    fs.writeFileSync(path.join(appRoot, 'app.old', 'ancient.py'), 'ancient')
    fs.mkdirSync(path.join(appRoot, 'app'), { recursive: true })
    fs.writeFileSync(path.join(appRoot, 'app', 'current.py'), 'current')

    callReplaceItem(makeService(appRoot), path.join(repoPath, 'app'), path.join(appRoot, 'app'))

    expect(fs.existsSync(path.join(appRoot, 'app', 'fresh.py'))).toBe(true)
    expect(fs.existsSync(path.join(appRoot, 'app', 'current.py'))).toBe(false)
    expect(fs.existsSync(path.join(appRoot, 'app', 'half.py'))).toBe(false)
    expect(fs.existsSync(path.join(appRoot, 'app.old'))).toBe(false)
  })

  it('源不存在时抛错，且目标原样不动', () => {
    const root = makeRoot()
    const appRoot = path.join(root, 'app-root')
    fs.mkdirSync(path.join(appRoot, 'app'), { recursive: true })
    fs.writeFileSync(path.join(appRoot, 'app', 'keep.py'), 'keep')

    expect(() =>
      callReplaceItem(makeService(appRoot), path.join(root, 'repo', 'app'), path.join(appRoot, 'app'))
    ).toThrow()

    // 关键：宁可停在旧版本，也不能把目标删空
    expect(fs.readFileSync(path.join(appRoot, 'app', 'keep.py'), 'utf8')).toBe('keep')
    expect(fs.existsSync(path.join(appRoot, 'app.new'))).toBe(false)
  })

  it('目标缺失而只剩 .old 时自愈，换入的是新版本', () => {
    const root = makeRoot()
    const repoPath = path.join(root, 'repo')
    const appRoot = path.join(root, 'app-root')
    fs.mkdirSync(path.join(repoPath, 'app'), { recursive: true })
    fs.writeFileSync(path.join(repoPath, 'app', 'fresh.py'), 'fresh')
    // 上次中断的现场：目标已改名成 .old，暂存还没改名成目标
    fs.mkdirSync(path.join(appRoot, 'app.old'), { recursive: true })
    fs.writeFileSync(path.join(appRoot, 'app.old', 'only.py'), 'only-copy')

    callReplaceItem(makeService(appRoot), path.join(repoPath, 'app'), path.join(appRoot, 'app'))

    expect(fs.existsSync(path.join(appRoot, 'app'))).toBe(true)
    expect(fs.readFileSync(path.join(appRoot, 'app', 'fresh.py'), 'utf8')).toBe('fresh')
    expect(fs.existsSync(path.join(appRoot, 'app', 'only.py'))).toBe(false)
    expect(fs.existsSync(path.join(appRoot, 'app.old'))).toBe(false)
  })

  it('目标缺失而只剩 .old 时，复制失败也不能把唯一的副本丢掉', () => {
    const root = makeRoot()
    const appRoot = path.join(root, 'app-root')
    // 仓库侧已经不可用（源条目不存在），现场仍是「目标缺失 + 只剩 .old」
    fs.mkdirSync(path.join(appRoot, 'app.old'), { recursive: true })
    fs.writeFileSync(path.join(appRoot, 'app.old', 'only.py'), 'only-copy')

    expect(() =>
      callReplaceItem(makeService(appRoot), path.join(root, 'repo', 'app'), path.join(appRoot, 'app'))
    ).toThrow()

    // 原来会先无条件删掉 .old，再在复制时抛错，目标从此永久消失
    expect(fs.readFileSync(path.join(appRoot, 'app', 'only.py'), 'utf8')).toBe('only-copy')
    expect(fs.existsSync(path.join(appRoot, 'app.old'))).toBe(false)
  })
})
