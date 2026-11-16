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
  return INSTALLED_VERSION
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
  // 清单不可用时禁止下载，拒绝篡改后仍可重试可信升级。
  it('代理源给出一套互相匹配的文件与哈希也装不上：清单从不问代理，exe 按可信哈希丢弃', async () => {
    const evil = 'evil-runtime-binary'
    let trustedSums: RuntimeTextFetchOutcome = { kind: 'failed', error: 'HTTP 503' }
    const sums = createSums(url => {
      // 代理要是被问到清单，会给出与自己那份 exe 匹配的哈希——这条路必须根本不存在。
      if (isProxyUrl(url)) return { kind: 'text', text: sumsFor(evil) }
      return trustedSums
    })
    const valid = createDownload(() => ({ success: true, content: NEW_BINARY }))

    const unavailable = await syncRuntimeBinary(
      syncOptions({ download: valid.download, fetchText: sums.fetchText })
    )

    expect(unavailable).toMatchObject({
      status: 'failed',
      code: RUNTIME_BINARY_DOWNLOAD_FAILED,
    })
    expect(unavailable.error).toContain('校验清单')
    expect(unavailable.error).toContain('HTTP 503')
    expect(sums.urls.some(isCnbUrl)).toBe(true)
    expect(sums.urls.some(isGithubUrl)).toBe(true)
    expect(valid.download).not.toHaveBeenCalled()
    expect(fs.readFileSync(runtimePath, 'utf8')).toBe(OLD_BINARY)
    expect(installDir()).toEqual(['auto-mas-runtime.exe'])

    trustedSums = { kind: 'text', text: sumsFor(NEW_BINARY) }
    const stub = createDownload(url =>
      isProxyUrl(url) ? { success: true, content: evil } : { success: false, error: 'HTTP 502' }
    )

    const outcome = await syncRuntimeBinary(
      syncOptions({ download: stub.download, fetchText: sums.fetchText })
    )

    expect(sums.urls.some(isProxyUrl)).toBe(false)
    expect(stub.urls.some(isProxyUrl)).toBe(true)
    expect(outcome.status).toBe('failed')
    expect(outcome.code).toBe(RUNTIME_BINARY_DOWNLOAD_FAILED)
    expect(outcome.error).toContain('SHA-256 不匹配')
    expect(fs.readFileSync(runtimePath, 'utf8')).toBe(OLD_BINARY)
    expect(installDir()).toEqual(['auto-mas-runtime.exe'])

    const upgraded = await syncRuntimeBinary(
      syncOptions({ download: valid.download, fetchText: sums.fetchText })
    )

    expect(upgraded).toEqual({ status: 'upgraded', target: TARGET })
    expect(sums.urls.every(url => isCnbUrl(url) || isGithubUrl(url))).toBe(true)
    expect(fs.readFileSync(runtimePath, 'utf8')).toBe(NEW_BINARY)
    expect(installDir()).toEqual(['auto-mas-runtime.exe'])
  })

  describe('在途互斥', () => {
    // 两条调用链共享一次替换与最终完成通知。
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
      expect(fs.readFileSync(runtimePath, 'utf8')).toBe(OLD_BINARY)
      expect(finish).toBeDefined()
      finish?.()

      const outcomes = await Promise.all([first, second])

      // 一份 exe，后来者没有再开任何下载；版本也只问了一轮（替换前一次、替换后确认一次）。
      expect(download).toHaveBeenCalledTimes(1)
      expect(readVersion).toHaveBeenCalledTimes(2)
      expect(outcomes[0]).toBe(outcomes[1])
      expect(outcomes[0].status).toBe('upgraded')
      expect(outcomes[0].target).toEqual(TARGET)
      expect(fs.readFileSync(runtimePath, 'utf8')).toBe(NEW_BINARY)
      expect(installDir()).toEqual(['auto-mas-runtime.exe'])
      expect(secondProgress).toContainEqual(expect.objectContaining({ progress: 50 }))
      expect(firstProgress.at(-1)).toMatchObject({
        phase: 'complete',
        progress: 100,
        targetVersion: TARGET_VERSION,
      })
      expect(secondProgress.at(-1)).toEqual(firstProgress.at(-1))
    })
  })

  describe('取消', () => {
    // 取消结果先返回，之后真实写完的下载也只能清理，不能替换。
    it('下载途中取消：不再等在途的下载，它结束后临时文件被清掉，exe 保持原样', async () => {
      let cancelled = false
      let finish: (() => void) | undefined
      let lateDownloadPath = ''
      const download = vi.fn(
        (_url: string, savePath: string) =>
          new Promise<{ success: boolean }>(resolve => {
            // exe 一开始下就取消；下载器没有取消接口，这里要等测试放行才写完。
            lateDownloadPath = savePath
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

      expect(lateDownloadPath.startsWith(`${runtimePath}.download-`)).toBe(true)
      expect(finish).toBeDefined()
      finish?.()
      expect(fs.readFileSync(lateDownloadPath, 'utf8')).toBe(NEW_BINARY)
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

    // 被占用的坏 exe 不能覆盖上次留下的可用备份。
    it('新文件挪不进去时把旧文件改回来，exe 保持原样', async () => {
      const { download } = createDownload(() => ({ success: true, content: NEW_BINARY }))
      renameHook.before = (from, to) => {
        if (isMoveIn(from, to)) {
          expect(fs.readFileSync(`${runtimePath}.old`, 'utf8')).toBe(OLD_BINARY)
          throw busyError()
        }
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

      renameHook.calls.length = 0
      fs.writeFileSync(runtimePath, 'broken-runtime-binary', 'utf8')
      fs.writeFileSync(`${runtimePath}.old`, OLD_BINARY, 'utf8')
      const versionOf = async (target: string) =>
        fs.readFileSync(target, 'utf8') === OLD_BINARY ? INSTALLED_VERSION : null
      const brokenInPlace = () => {
        try {
          return fs.readFileSync(runtimePath, 'utf8') === 'broken-runtime-binary'
        } catch {
          return false
        }
      }
      // 坏文件删不掉、备份改不回；挪开坏文件后再允许恢复。
      rmHook.before = target => {
        if (target === runtimePath && brokenInPlace()) throw busyError()
      }
      renameHook.before = (from, to) => {
        if (isRestore(from, to) && brokenInPlace()) throw busyError()
        if (isMoveIn(from, to)) {
          expect(fs.readFileSync(`${runtimePath}.old`, 'utf8')).toBe(OLD_BINARY)
        }
      }

      const withBackup = await syncRuntimeBinary(syncOptions({ download, readVersion: versionOf }))

      expect(withBackup.status).toBe('failed')
      expect(withBackup.code).toBe(RUNTIME_BINARY_REPLACE_FAILED)
      expect(withBackup.error).toContain('无法运行')
      expect(fs.readFileSync(runtimePath, 'utf8')).toBe(OLD_BINARY)
      expect(installDir()).toEqual(['auto-mas-runtime.exe'])
      expect(renameHook.calls).not.toContainEqual([runtimePath, `${runtimePath}.old`])
      expect(renameHook.calls).toContainEqual([runtimePath, expect.stringContaining('.download')])
    })

    // 可信哈希通过后仍须保留旧文件，直到新 exe 实际通过版本探测。
    it('新文件挪进来了却跑不起来：换回旧文件并报失败，提示查安全软件', async () => {
      newBinaryVersion = null
      const { download } = createDownload(() => ({ success: true, content: NEW_BINARY }))

      const outcome = await syncRuntimeBinary(
        syncOptions({
          download,
          readVersion: async target => {
            if (fs.readFileSync(target, 'utf8') === NEW_BINARY) {
              expect(fs.readFileSync(`${runtimePath}.old`, 'utf8')).toBe(OLD_BINARY)
            }
            return readVersion(target)
          },
        })
      )

      expect(outcome.status).toBe('failed')
      expect(outcome.code).toBe(RUNTIME_BINARY_REPLACE_FAILED)
      expect(outcome.error).toContain('无法运行')
      expect(outcome.error).toContain('已恢复原来的文件')
      expect(outcome.error).toContain('安全软件')
      expect(fs.readFileSync(runtimePath, 'utf8')).toBe(OLD_BINARY)
      expect(installDir()).toEqual(['auto-mas-runtime.exe'])
    })
  })
})
