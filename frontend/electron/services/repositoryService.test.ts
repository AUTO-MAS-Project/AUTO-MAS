import * as fs from 'fs'
import * as os from 'os'
import * as path from 'path'
import { EventEmitter } from 'events'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vite-plus/test'

import { MirrorService } from './mirrorService'
import { RepositoryService } from './repositoryService'

const faults = vi.hoisted(() => ({
  deniedPath: '',
  trackBranch: false,
  beforeRemove: null as ((target: string) => Promise<void>) | null,
}))
const spawnMock = vi.hoisted(() => vi.fn())

vi.mock('electron', () => ({ app: { isPackaged: false } }))
vi.mock('child_process', () => ({ spawn: spawnMock }))
vi.mock('./logger', () => ({
  getLogger: () => ({ info: vi.fn(), warn: vi.fn(), error: vi.fn() }),
}))
vi.mock('fs', async importOriginal => {
  const actual = await importOriginal<typeof import('fs')>()
  const hasReadOnlyFile = (target: fs.PathLike): boolean => {
    if (!actual.existsSync(target)) return false
    const stat = actual.statSync(target)
    return stat.isDirectory()
      ? actual.readdirSync(target).some(name => hasReadOnlyFile(path.join(String(target), name)))
      : (stat.mode & 0o200) === 0
  }
  return {
    ...actual,
    // Electron 的 Windows 构建会拒绝同步删除只读 Git 对象，普通 Node 不会。
    rmSync: (target: fs.PathLike, options?: fs.RmOptions) => {
      if (String(target) === faults.deniedPath) {
        throw Object.assign(new Error('repository is locked'), { code: 'EBUSY' })
      }
      if (hasReadOnlyFile(target)) {
        throw Object.assign(new Error('read-only Git object'), { code: 'EPERM' })
      }
      return actual.rmSync(target, options)
    },
    promises: {
      ...actual.promises,
      rm: async (target: fs.PathLike, options?: fs.RmOptions) => {
        await faults.beforeRemove?.(String(target))
        if (String(target) === faults.deniedPath) {
          throw Object.assign(new Error('repository is locked'), { code: 'EBUSY' })
        }
        return actual.promises.rm(target, options)
      },
    },
  }
})

let workspace: string
let service: RepositoryService

function writeFile(relativePath: string, content: string, readOnly = false) {
  const target = path.join(workspace, relativePath)
  fs.mkdirSync(path.dirname(target), { recursive: true })
  fs.writeFileSync(target, content)
  if (readOnly) fs.chmodSync(target, 0o444)
}

function prepareSource() {
  writeFile('repo/.git/HEAD', 'new-head')
  writeFile('repo/.git/objects/new-object', 'new-object', true)
  writeFile('repo/app/marker.txt', 'new-code')
}

beforeEach(() => {
  faults.deniedPath = ''
  faults.trackBranch = false
  faults.beforeRemove = null
  workspace = fs.mkdtempSync(path.join(os.tmpdir(), 'mas-repository-'))
  service = new RepositoryService(workspace, new MirrorService(workspace))
  spawnMock.mockImplementation((_exe: string, args: string[]) => {
    const proc = Object.assign(new EventEmitter(), {
      stdout: new EventEmitter(),
      kill: vi.fn(),
    })
    queueMicrotask(() => {
      if (args[0] === 'clone') prepareSource()
      if (args[0] === 'ls-remote') proc.stdout.emit('data', `hash\trefs/heads/${args[3]}`)
      if (args[0] === 'branch') proc.stdout.emit('data', 'dev\n')
      if (args[0] === 'checkout' && faults.trackBranch) {
        writeFile('repo/.git/HEAD', args[2])
        writeFile('repo/app/marker.txt', args[2])
      }
      proc.emit('close', 0)
    })
    return proc
  })
})

afterEach(async () => {
  faults.deniedPath = ''
  faults.beforeRemove = null
  await fs.promises.rm(workspace, { recursive: true, force: true })
  vi.clearAllMocks()
})

describe('legacy repository initialization', () => {
  it('serializes pulls across service instances sharing the same installation', async () => {
    prepareSource()
    writeFile('.git/HEAD', 'old-head')
    faults.trackBranch = true
    let release: () => void = () => {}
    let entered: () => void = () => {}
    const blocked = new Promise<void>(resolve => {
      release = resolve
    })
    const deleting = new Promise<void>(resolve => {
      entered = resolve
    })
    faults.beforeRemove = async target => {
      if (target === path.join(workspace, '.git')) {
        faults.beforeRemove = null
        entered()
        await blocked
      }
    }
    let firstInstalled = ''
    const first = service.pullRepository(progress => {
      if (progress.stage === 'deploy' && progress.progress === 100) {
        firstInstalled = fs.readFileSync(path.join(workspace, 'app/marker.txt'), 'utf8')
      }
    })
    await deleting
    const secondProgress = vi.fn()
    const other = new RepositoryService(
      `${workspace}${path.sep}.`,
      new MirrorService(workspace),
      'other'
    )
    const second = other.pullRepository(secondProgress)
    let results
    try {
      expect(secondProgress).not.toHaveBeenCalled()
    } finally {
      release()
      results = await Promise.all([first, second])
    }

    expect(results).toEqual([{ success: true }, { success: true }])
    expect(firstInstalled).toBe('dev')
    expect(fs.readFileSync(path.join(workspace, '.git/HEAD'), 'utf8')).toBe('other')
    expect(fs.readFileSync(path.join(workspace, 'app/marker.txt'), 'utf8')).toBe('other')
  })

  it('releases a failed pull so the next instance can retry', async () => {
    prepareSource()
    writeFile('.git/HEAD', 'old-head')
    faults.deniedPath = path.join(workspace, '.git')
    const first = service.pullRepository()
    const retry = new RepositoryService(workspace, new MirrorService(workspace)).pullRepository(
      progress => {
        if (progress.stage === 'check' && progress.progress === 0) faults.deniedPath = ''
      }
    )

    expect(await first).toEqual({ success: false, error: 'repository is locked' })
    expect(await retry).toEqual({ success: true })
    expect(fs.readFileSync(path.join(workspace, 'app/marker.txt'), 'utf8')).toBe('new-code')
  })

  it('allows a different installation to proceed while a pull is blocked', async () => {
    prepareSource()
    writeFile('.git/HEAD', 'old-head')
    writeFile('independent/repo/.git/HEAD', 'independent-head')
    writeFile('independent/repo/app/marker.txt', 'independent-code')
    let release: () => void = () => {}
    let entered: () => void = () => {}
    const blocked = new Promise<void>(resolve => {
      release = resolve
    })
    const deleting = new Promise<void>(resolve => {
      entered = resolve
    })
    faults.beforeRemove = async target => {
      if (target === path.join(workspace, '.git')) {
        faults.beforeRemove = null
        entered()
        await blocked
      }
    }
    const first = service.pullRepository()
    await deleting
    const independentRoot = path.join(workspace, 'independent')
    const progress = vi.fn()
    const independent = new RepositoryService(
      independentRoot,
      new MirrorService(independentRoot)
    ).pullRepository(progress)
    try {
      await vi.waitFor(() => expect(progress).toHaveBeenCalled())
      expect(await independent).toEqual({ success: true })
      expect(fs.readFileSync(path.join(independentRoot, 'app/marker.txt'), 'utf8')).toBe(
        'independent-code'
      )
    } finally {
      release()
      await Promise.all([first, independent])
    }
  })

  it('deploys new code over installed read-only Git objects', async () => {
    prepareSource()
    writeFile('.git/objects/old-object', 'old-object', true)
    writeFile('app/marker.txt', 'old-code')
    writeFile('config/keep.txt', 'user-config')

    expect(await service.pullRepository()).toEqual({ success: true })
    expect(fs.readFileSync(path.join(workspace, '.git/HEAD'), 'utf8')).toBe('new-head')
    expect(fs.existsSync(path.join(workspace, '.git/objects/old-object'))).toBe(false)
    expect(fs.readFileSync(path.join(workspace, 'app/marker.txt'), 'utf8')).toBe('new-code')
    expect(fs.readFileSync(path.join(workspace, 'config/keep.txt'), 'utf8')).toBe('user-config')
  })

  it('recreates an invalid repository containing read-only files', async () => {
    writeFile('repo/old-object', 'orphaned-object', true)

    expect(await service.pullRepository()).toEqual({ success: true })
    expect(fs.existsSync(path.join(workspace, 'repo/old-object'))).toBe(false)
    expect(fs.readFileSync(path.join(workspace, 'app/marker.txt'), 'utf8')).toBe('new-code')
  })

  it('reports a real cleanup failure and leaves installed code unchanged', async () => {
    prepareSource()
    writeFile('.git/HEAD', 'old-head')
    writeFile('app/marker.txt', 'old-code')
    faults.deniedPath = path.join(workspace, '.git')

    expect(await service.pullRepository()).toEqual({
      success: false,
      error: 'repository is locked',
    })
    expect(fs.readFileSync(path.join(workspace, '.git/HEAD'), 'utf8')).toBe('old-head')
    expect(fs.readFileSync(path.join(workspace, 'app/marker.txt'), 'utf8')).toBe('old-code')
  })
})
