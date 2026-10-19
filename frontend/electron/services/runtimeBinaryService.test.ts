import * as crypto from 'crypto'
import * as fs from 'fs'
import * as os from 'os'
import * as path from 'path'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vite-plus/test'

import { RUNTIME_EXE_ENV } from './runtime'
import {
  RUNTIME_BINARY_CANCELLED,
  RUNTIME_BINARY_DOWNLOAD_FAILED,
  RUNTIME_BINARY_REPLACE_FAILED,
  buildRuntimeBinarySources,
  runtimeAssetName,
  syncRuntimeBinary,
  type RuntimeBinarySyncOptions,
  type RuntimeBinarySyncProgress,
  type RuntimeTextFetchOutcome,
  type RuntimeTextFetcher,
} from './runtimeBinaryService'

vi.mock('electron', () => ({ app: { isPackaged: false } }))
/**
 * `fs.renameSync` 的前置钩子：让用例模拟「目标 exe 被占用」——真实占用只能靠起一个进程，
 * 这里在真正 rename 之前按参数决定抛不抛 EBUSY，其余行为照旧走真实文件系统。
 */
const renameHook = vi.hoisted(() => ({
  before: null as ((from: string, to: string) => void) | null,
  calls: [] as [string, string][],
}))
/** 同理给 `fs.rmSync` 一个前置钩子，模拟「被占用的文件删不掉」。 */
const rmHook = vi.hoisted(() => ({
  before: null as ((target: string) => void) | null,
}))
vi.mock('fs', async importOriginal => {
  const actual = await importOriginal<typeof import('fs')>()
  return {
    ...actual,
    renameSync: (from: fs.PathLike, to: fs.PathLike) => {
      renameHook.calls.push([String(from), String(to)])
      renameHook.before?.(String(from), String(to))
      return actual.renameSync(from, to)
    },
    rmSync: (target: fs.PathLike, options?: fs.RmOptions) => {
      rmHook.before?.(String(target))
      return actual.rmSync(target, options)
    },
  }
})
vi.mock('./logger', () => ({
  getLogger: () => ({
    error: vi.fn(),
    warn: vi.fn(),
    info: vi.fn(),
    verbose: vi.fn(),
    debug: vi.fn(),
    silly: vi.fn(),
  }),
}))

const OLD_BINARY = 'old-runtime-binary'
const NEW_BINARY = 'new-runtime-binary'
const INSTALLED_VERSION = 'v0.1.4'
/** 线上最新版：旧实现里是「钉扎」，现在由发布列表解析得到。 */
const TARGET_VERSION = 'v0.1.5'

function sha256(content: string): string {
  return crypto.createHash('sha256').update(content).digest('hex')
}

const TARGET_ASSET = runtimeAssetName(TARGET_VERSION)

/** 照着真实 Release 的 `SHA256SUMS.txt` 造：`<hash>  <asset>`，CRLF 结尾。 */
function sumsFor(content: string, asset = TARGET_ASSET): string {
  return `${sha256(content)}  ${asset}\r\n`
}

const isCnbUrl = (url: string) => url.includes('cnb.cool')
const isGithubUrl = (url: string) => url.startsWith('https://github.com/')
const isProxyUrl = (url: string) => url.includes('gh-proxy.com')

/** 每个用例一套独立的安装目录与受管源码目录。 */
let workspace: string
let runtimePath: string
/** 磁盘上那个 exe 自报的版本，用例按需改写。 */
let installedVersion: string | null
/** 换上新文件之后它自报的版本；设成 null 模拟「新文件跑不起来」。 */
let newBinaryVersion: string | null

type DownloadPlan = (url: string) => { success: boolean; content?: string; error?: string }

/** 造一个「写入指定内容」的 exe 下载器桩，并记录被请求过的 URL。 */
function createDownload(plan: DownloadPlan) {
  const urls: string[] = []
  const download = vi.fn(
    async (url: string, savePath: string, onProgress?: (p: { progress: number }) => void) => {
      urls.push(url)
      const outcome = plan(url)
      if (!outcome.success) return { success: false, error: outcome.error ?? '下载失败' }
      onProgress?.({ progress: 50 })
      fs.writeFileSync(savePath, outcome.content ?? '', 'utf8')
      return { success: true }
    }
  )
  return { download, urls }
}

type SumsPlan = (url: string) => RuntimeTextFetchOutcome

/**
 * 可信来源的校验清单桩：缺省 CNB 与 GitHub 都按 NEW_BINARY 的哈希照真实格式返回；
 * 要模拟清单出问题的用例自己传 plan。记录被问过的 URL，用来断言代理源没被问。
 */
function createSums(plan: SumsPlan = () => ({ kind: 'text', text: sumsFor(NEW_BINARY) })) {
  const urls: string[] = []
  const fetchText: RuntimeTextFetcher = vi.fn(async (url: string) => {
    urls.push(url)
    return plan(url)
  })
  return { fetchText, urls }
}

/**
 * 版本查询走桩，测试里那个 exe 只是个文本文件，真跑不起来：内容是 NEW_BINARY 就按
 * 「换上的新文件」回答，其余按「原来那份」回答。
 */
const readVersion = vi.fn(async (target: string) => {
  try {
    if (fs.readFileSync(target, 'utf8') === NEW_BINARY) return newBinaryVersion
  } catch {
    // 文件不存在：按原来那份回答。
  }
  return installedVersion
})

const TARGET = { version: TARGET_VERSION }

function syncOptions(extra: Partial<RuntimeBinarySyncOptions> = {}): RuntimeBinarySyncOptions {
  return {
    runtimePath,
    appRoot: workspace,
    target: TARGET,
    readVersion,
    fetchText: createSums().fetchText,
    ...extra,
  }
}

const installDir = () => fs.readdirSync(path.dirname(runtimePath))

beforeEach(() => {
  workspace = fs.mkdtempSync(path.join(os.tmpdir(), 'auto-mas-runtime-binary-'))
  runtimePath = path.join(workspace, 'resources', 'auto-mas-runtime.exe')
  installedVersion = INSTALLED_VERSION
  newBinaryVersion = TARGET_VERSION
  readVersion.mockClear()
  fs.mkdirSync(path.dirname(runtimePath), { recursive: true })
  fs.writeFileSync(runtimePath, OLD_BINARY, 'utf8')
  delete process.env[RUNTIME_EXE_ENV]
})

afterEach(() => {
  delete process.env[RUNTIME_EXE_ENV]
  renameHook.before = null
  renameHook.calls.length = 0
  rmHook.before = null
  fs.rmSync(workspace, { recursive: true, force: true })
})

// ==================== 同步 ====================

describe('syncRuntimeBinary', () => {
  it('版本较旧时先取可信清单，再下载线上最新版并替换', async () => {
    const { download, urls } = createDownload(() => ({ success: true, content: NEW_BINARY }))
    const sums = createSums()
    const progress: RuntimeBinarySyncProgress[] = []

    const outcome = await syncRuntimeBinary(
      syncOptions({
        download,
        fetchText: sums.fetchText,
        onProgress: update => progress.push(update),
      })
    )

    expect(outcome.status).toBe('upgraded')
    expect(outcome.target).toEqual(TARGET)
    // 清单只问了 CNB 与 GitHub；exe 第一个源就成功，不该继续往下试。
    expect(sums.urls.every(url => isCnbUrl(url) || isGithubUrl(url))).toBe(true)
    const [first] = buildRuntimeBinarySources(TARGET_VERSION)
    expect(urls).toEqual([first.url])
    expect(fs.readFileSync(runtimePath, 'utf8')).toBe(NEW_BINARY)
    expect(progress.at(-1)).toEqual({
      progress: 100,
      message: `Runtime 已更新到 ${TARGET_VERSION}`,
    })
  })

  it('装的是比线上最新更新的一版：保留本地，不下载也不降级', async () => {
    installedVersion = 'v0.9.0'
    const { download } = createDownload(() => ({ success: true, content: NEW_BINARY }))

    const outcome = await syncRuntimeBinary(syncOptions({ download }))

    expect(outcome).toEqual({ status: 'current', target: TARGET })
    expect(download).not.toHaveBeenCalled()
    expect(fs.readFileSync(runtimePath, 'utf8')).toBe(OLD_BINARY)
    expect(installDir()).toEqual(['auto-mas-runtime.exe'])
  })

  it('代理源给出一套互相匹配的文件与哈希也装不上：清单从不问代理，exe 按可信哈希丢弃', async () => {
    const evil = 'evil-runtime-binary'
    const sums = createSums(url => {
      // 代理要是被问到清单，会给出与自己那份 exe 匹配的哈希——这条路必须根本不存在。
      if (isProxyUrl(url)) return { kind: 'text', text: sumsFor(evil) }
      return { kind: 'text', text: sumsFor(NEW_BINARY) }
    })
    const stub = createDownload(url =>
      isProxyUrl(url) ? { success: true, content: evil } : { success: false, error: 'HTTP 502' }
    )

    const outcome = await syncRuntimeBinary(
      syncOptions({ download: stub.download, fetchText: sums.fetchText })
    )

    expect(sums.urls.some(isProxyUrl)).toBe(false)
    expect(outcome.status).toBe('failed')
    expect(outcome.code).toBe(RUNTIME_BINARY_DOWNLOAD_FAILED)
    expect(outcome.error).toContain('SHA-256 不匹配')
    expect(fs.readFileSync(runtimePath, 'utf8')).toBe(OLD_BINARY)
    expect(installDir()).toEqual(['auto-mas-runtime.exe'])
  })

  it('CNB 与 GitHub 的清单都取不到时一个 exe 都不下，失败原因指向清单', async () => {
    const sums = createSums(() => ({ kind: 'failed', error: 'HTTP 503' }))
    const stub = createDownload(() => ({ success: true, content: NEW_BINARY }))

    const outcome = await syncRuntimeBinary(
      syncOptions({ download: stub.download, fetchText: sums.fetchText })
    )

    expect(outcome.status).toBe('failed')
    expect(outcome.code).toBe(RUNTIME_BINARY_DOWNLOAD_FAILED)
    expect(outcome.error).toContain('校验清单')
    expect(outcome.error).toContain('HTTP 503')
    expect(stub.download).not.toHaveBeenCalled()
    expect(fs.readFileSync(runtimePath, 'utf8')).toBe(OLD_BINARY)
    expect(installDir()).toEqual(['auto-mas-runtime.exe'])
  })

  describe('在途互斥', () => {
    it('并发两次同步只下载一次，后来者拿到同一个结果与进度', async () => {
      let finish: (() => void) | undefined
      const download = vi.fn(
        (_url: string, savePath: string, onProgress?: (p: { progress: number }) => void) =>
          new Promise<{ success: boolean }>(resolve => {
            finish = () => {
              onProgress?.({ progress: 50 })
              fs.writeFileSync(savePath, NEW_BINARY, 'utf8')
              resolve({ success: true })
            }
          })
      )
      const firstProgress: RuntimeBinarySyncProgress[] = []
      const secondProgress: RuntimeBinarySyncProgress[] = []

      const first = syncRuntimeBinary(
        syncOptions({ download, onProgress: update => firstProgress.push(update) })
      )
      const second = syncRuntimeBinary(
        syncOptions({ download, onProgress: update => secondProgress.push(update) })
      )
      await vi.waitFor(() => expect(download).toHaveBeenCalledTimes(1))
      expect(finish).toBeDefined()
      finish?.()

      const outcomes = await Promise.all([first, second])

      // 一份 exe，后来者没有再开任何下载；版本也只问了一轮（替换前一次、替换后确认一次）。
      expect(download).toHaveBeenCalledTimes(1)
      expect(readVersion).toHaveBeenCalledTimes(2)
      expect(outcomes[0]).toBe(outcomes[1])
      expect(outcomes[0].status).toBe('upgraded')
      expect(fs.readFileSync(runtimePath, 'utf8')).toBe(NEW_BINARY)
      expect(secondProgress).toContainEqual(expect.objectContaining({ progress: 50 }))
      expect(secondProgress.at(-1)).toEqual(firstProgress.at(-1))
    })
  })

  describe('取消', () => {
    it('下载途中取消：不再等在途的下载，它结束后临时文件被清掉，exe 保持原样', async () => {
      let cancelled = false
      let finish: (() => void) | undefined
      const download = vi.fn(
        (_url: string, savePath: string) =>
          new Promise<{ success: boolean }>(resolve => {
            // exe 一开始下就取消；下载器没有取消接口，这里要等测试放行才写完。
            cancelled = true
            finish = () => {
              fs.writeFileSync(savePath, NEW_BINARY, 'utf8')
              resolve({ success: true })
            }
          })
      )
      const startedAt = Date.now()

      const outcome = await syncRuntimeBinary(
        syncOptions({ download, isCancelled: () => cancelled })
      )

      expect(outcome.status).toBe('cancelled')
      expect(outcome.code).toBe(RUNTIME_BINARY_CANCELLED)
      // 取消判据每 250ms 轮询一次，不该等到单源上限。
      expect(Date.now() - startedAt).toBeLessThan(5000)
      expect(download).toHaveBeenCalledTimes(1)
      expect(fs.readFileSync(runtimePath, 'utf8')).toBe(OLD_BINARY)

      finish?.()
      await vi.waitFor(() => expect(installDir()).toEqual(['auto-mas-runtime.exe']))
      expect(fs.readFileSync(runtimePath, 'utf8')).toBe(OLD_BINARY)
    })
  })

  describe('替换与备份', () => {
    const busyError = () =>
      Object.assign(new Error('EBUSY: resource busy or locked'), { code: 'EBUSY' })

    const isMoveIn = (from: string, to: string) => to === runtimePath && from.includes('.download')
    const isRestore = (from: string, to: string) =>
      from === `${runtimePath}.old` && to === runtimePath

    it('新文件挪不进去时把旧文件改回来，exe 保持原样', async () => {
      const { download } = createDownload(() => ({ success: true, content: NEW_BINARY }))
      renameHook.before = (from, to) => {
        if (isMoveIn(from, to)) throw busyError()
      }

      const outcome = await syncRuntimeBinary(syncOptions({ download }))

      expect(outcome.status).toBe('failed')
      expect(outcome.code).toBe(RUNTIME_BINARY_REPLACE_FAILED)
      expect(outcome.error).toContain('EBUSY')
      // 占用是能自己解决的：告诉用户结束哪个进程。
      expect(outcome.error).toContain('auto-mas-runtime.exe 进程')
      expect(outcome.error).toContain(runtimePath)
      expect(fs.readFileSync(runtimePath, 'utf8')).toBe(OLD_BINARY)
      expect(installDir()).toEqual(['auto-mas-runtime.exe'])
      // 回滚：让路的 .old 被改回 exe 路径。
      expect(renameHook.calls).toContainEqual([`${runtimePath}.old`, runtimePath])
    })

    it('新文件挪进来了却跑不起来：换回旧文件并报失败，提示查安全软件', async () => {
      newBinaryVersion = null
      const { download } = createDownload(() => ({ success: true, content: NEW_BINARY }))

      const outcome = await syncRuntimeBinary(syncOptions({ download }))

      expect(outcome.status).toBe('failed')
      expect(outcome.code).toBe(RUNTIME_BINARY_REPLACE_FAILED)
      expect(outcome.error).toContain('无法运行')
      expect(outcome.error).toContain('已恢复原来的文件')
      expect(outcome.error).toContain('安全软件')
      expect(fs.readFileSync(runtimePath, 'utf8')).toBe(OLD_BINARY)
      expect(installDir()).toEqual(['auto-mas-runtime.exe'])
    })

    it('坏 exe 被占用换不回备份时，替换不拿坏文件覆盖备份；新文件又跑不起来就恢复备份', async () => {
      fs.writeFileSync(runtimePath, 'broken-runtime-binary', 'utf8')
      fs.writeFileSync(`${runtimePath}.old`, OLD_BINARY, 'utf8')
      const versionOf = vi.fn(async (target: string) => {
        const content = fs.readFileSync(target, 'utf8')
        return content === OLD_BINARY ? INSTALLED_VERSION : null
      })
      // 坏文件被占用：删不掉，.old 也改不回正式路径（目标还在）；坏文件挪开之后一切放行。
      const brokenInPlace = () => {
        try {
          return fs.readFileSync(runtimePath, 'utf8') === 'broken-runtime-binary'
        } catch {
          return false
        }
      }
      rmHook.before = target => {
        if (target === runtimePath && brokenInPlace()) throw busyError()
      }
      renameHook.before = (from, to) => {
        if (isRestore(from, to) && brokenInPlace()) throw busyError()
      }
      const { download } = createDownload(() => ({ success: true, content: NEW_BINARY }))

      const outcome = await syncRuntimeBinary(syncOptions({ download, readVersion: versionOf }))

      // 新文件也跑不起来 → 恢复的是最后一份能跑的 OLD_BINARY，而不是那份坏文件。
      expect(outcome.status).toBe('failed')
      expect(outcome.code).toBe(RUNTIME_BINARY_REPLACE_FAILED)
      expect(fs.readFileSync(runtimePath, 'utf8')).toBe(OLD_BINARY)
      expect(installDir()).toEqual(['auto-mas-runtime.exe'])
      // 让路时坏文件没有被改名成 .old，而是按半截下载的名字挪开后清掉。
      expect(renameHook.calls).not.toContainEqual([runtimePath, `${runtimePath}.old`])
      expect(renameHook.calls).toContainEqual([runtimePath, expect.stringContaining('.download')])
    })
  })
})
