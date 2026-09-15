import { EventEmitter } from 'events'
import * as fs from 'fs'
import * as os from 'os'
import * as path from 'path'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('child_process', () => ({
  spawn: vi.fn(),
  execFile: vi.fn((_file: string, _args: string[], cb: (err: Error | null) => void) =>
    cb(null)
  ),
}))

import { spawn } from 'child_process'
import { RepositoryService } from './repositoryService'

// ==================== 测试辅助 ====================

interface FakeChild extends EventEmitter {
  pid: number
  stdout: EventEmitter
  stderr: EventEmitter
  kill: ReturnType<typeof vi.fn>
}

function fakeChild(pid = 1234): FakeChild {
  const child = new EventEmitter() as unknown as FakeChild
  child.pid = pid
  child.stdout = new EventEmitter()
  child.stderr = new EventEmitter()
  child.kill = vi.fn(() => true)
  return child
}

const mirrorService = {
  getMirrors: () => [{ key: 'cnb', name: 'CNB', url: 'https://example.invalid/a.git', type: 'mirror' }],
}

describe('RepositoryService 失败恢复', () => {
  let appRoot: string
  let repoPath: string

  beforeEach(() => {
    appRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'mas-repo-'))
    repoPath = path.join(appRoot, 'repo')
    vi.clearAllMocks()
  })

  afterEach(() => {
    fs.rmSync(appRoot, { recursive: true, force: true })
  })

  it('git status 判定损坏后自动清理残缺 repo，无需手动删除', async () => {
    // 造一个带 .git 但内容损坏的仓库
    fs.mkdirSync(path.join(repoPath, '.git'), { recursive: true })
    fs.writeFileSync(path.join(repoPath, '.git', 'broken'), 'x')

    vi.mocked(spawn).mockImplementation(() => {
      const child = fakeChild()
      setImmediate(() => child.emit('close', 1)) // git status 失败
      return child as unknown as ReturnType<typeof spawn>
    })

    const service = new RepositoryService(appRoot, mirrorService as never, 'dev')
    const result = await (service as unknown as {
      checkRepository: () => Promise<{ exists: boolean; isHealthy: boolean }>
    }).checkRepository()

    expect(result.exists).toBe(false)
    expect(result.isHealthy).toBe(false)
    expect(fs.existsSync(repoPath)).toBe(false)
  })

  it('clone 失败后清理半成品仓库目录，下次可重新克隆', async () => {
    vi.mocked(spawn).mockImplementation((_cmd, args) => {
      const child = fakeChild()
      const argv = args as string[]
      setImmediate(() => {
        if (argv?.includes('ls-remote')) {
          child.stdout.emit('data', Buffer.from('refs/heads/dev'))
          child.emit('close', 0)
        } else {
          // 模拟 clone 进行到一半：写出半成品后失败退出
          fs.mkdirSync(path.join(repoPath, '.git'), { recursive: true })
          fs.writeFileSync(path.join(repoPath, '.git', 'partial'), 'x')
          child.emit('close', 1)
        }
      })
      return child as unknown as ReturnType<typeof spawn>
    })

    const service = new RepositoryService(appRoot, mirrorService as never, 'dev')
    const result = await service.pullRepository()

    expect(result.success).toBe(false)
    // 关键断言：失败后残留已被清理，用户不必手动删 repo
    expect(fs.existsSync(repoPath)).toBe(false)
  })
})
