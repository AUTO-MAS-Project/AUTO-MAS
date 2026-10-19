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
  RUNTIME_LATEST_UNAVAILABLE,
  alignRuntimeBinaryWithLatest,
  buildRuntimeBinarySources,
  buildRuntimeSumsSources,
  fetchTrustedRuntimeHash,
  hashFileSha256,
  parseRuntimeSums,
  runtimeAssetName,
  syncRuntimeBinary,
  type RuntimeBinaryAlignOptions,
  type RuntimeBinarySyncOptions,
  type RuntimeBinarySyncProgress,
  type RuntimeBinarySyncResult,
  type RuntimeTextFetchOutcome,
  type RuntimeTextFetcher,
} from './runtimeBinaryService'
import type { LatestRuntimeVersionLookup } from './runtimeReleaseService'

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

// ==================== 校验清单 ====================

describe('parseRuntimeSums', () => {
  it('按资产名取出对应行的哈希，容忍 CRLF 与大写', () => {
    const text = `${'A'.repeat(64)}  other.exe\r\n${sha256(NEW_BINARY).toUpperCase()}  ${TARGET_ASSET}\r\n`

    expect(parseRuntimeSums(text, TARGET_ASSET)).toBe(sha256(NEW_BINARY))
  })

  it.each([
    ['清单为空', ''],
    ['清单里没有这个资产', sumsFor(NEW_BINARY, 'auto-mas-runtime-v9.9.9.exe')],
    ['哈希长度不对', `abc123  ${TARGET_ASSET}\n`],
    ['哈希含非十六进制字符', `${'z'.repeat(64)}  ${TARGET_ASSET}\n`],
    ['只有哈希没有文件名', `${sha256(NEW_BINARY)}\n`],
    ['拿到的是错误页', '<html><body>404 Not Found</body></html>'],
  ])('%s 时返回 null', (_label, text) => {
    expect(parseRuntimeSums(text, TARGET_ASSET)).toBeNull()
  })
})

// ==================== 下载源 ====================

describe('buildRuntimeBinarySources', () => {
  it('CNB 排第一，随后是代理源，官方源永远兜底在最后', () => {
    const sources = buildRuntimeBinarySources(TARGET_VERSION)

    expect(sources.map(source => source.key)).toEqual([
      'cnb',
      'ghproxy_cloudflare',
      'ghproxy_fastly',
      'ghproxy_edgeone',
      'github',
    ])
    expect(sources[0].url).toBe(
      'https://cnb.cool/AUTO-MAS-Project/AUTO-MAS-Runtime/-/releases/download/v0.1.5/auto-mas-runtime-v0.1.5.exe'
    )
    expect(sources.at(-1)?.url).toBe(
      'https://github.com/AUTO-MAS-Project/AUTO-MAS-Runtime/releases/download/v0.1.5/auto-mas-runtime-v0.1.5.exe'
    )
  })
})

describe('buildRuntimeSumsSources', () => {
  it('校验清单只从 CNB 与 GitHub 取，代理源一个都没有', () => {
    const sources = buildRuntimeSumsSources(TARGET_VERSION)

    expect(sources.map(source => source.key)).toEqual(['cnb', 'github'])
    expect(sources[0].url).toBe(
      'https://cnb.cool/AUTO-MAS-Project/AUTO-MAS-Runtime/-/releases/download/v0.1.5/SHA256SUMS.txt'
    )
    expect(sources[1].url).toBe(
      'https://github.com/AUTO-MAS-Project/AUTO-MAS-Runtime/releases/download/v0.1.5/SHA256SUMS.txt'
    )
    expect(sources.some(source => isProxyUrl(source.url))).toBe(false)
  })
})

// ==================== 可信哈希 ====================

describe('fetchTrustedRuntimeHash', () => {
  it('两个可信来源并行，先给出有效清单的胜出', async () => {
    const { fetchText, urls } = createSums(url =>
      isCnbUrl(url)
        ? { kind: 'failed', error: 'ECONNRESET' }
        : { kind: 'text', text: sumsFor(NEW_BINARY) }
    )

    const lookup = await fetchTrustedRuntimeHash(TARGET_VERSION, { fetchText })

    expect(lookup).toEqual({ status: 'found', hash: sha256(NEW_BINARY), source: 'github' })
    expect(urls).toHaveLength(2)
    expect(urls.some(isProxyUrl)).toBe(false)
  })

  it('该 Release 没有清单（两源都 404）时按取不到处理', async () => {
    const { fetchText } = createSums(() => ({ kind: 'missing' }))

    const lookup = await fetchTrustedRuntimeHash(TARGET_VERSION, { fetchText })

    expect(lookup.status).toBe('unavailable')
    if (lookup.status !== 'unavailable') return
    expect(lookup.error).toContain('没有校验清单')
  })

  it('清单是错误页或缺该资产时不算有效，两源都不行就取不到', async () => {
    const { fetchText } = createSums(url =>
      isCnbUrl(url)
        ? { kind: 'text', text: '<html>403</html>' }
        : { kind: 'text', text: sumsFor(NEW_BINARY, 'auto-mas-runtime-v0.1.4.exe') }
    )

    const lookup = await fetchTrustedRuntimeHash(TARGET_VERSION, { fetchText })

    expect(lookup.status).toBe('unavailable')
    if (lookup.status !== 'unavailable') return
    expect(lookup.error).toContain(`清单里没有 ${TARGET_ASSET} 的有效 SHA-256`)
  })
})

// ==================== 同步 ====================

describe('syncRuntimeBinary', () => {
  it('exe 自报的版本就是线上最新版时不下载', async () => {
    installedVersion = TARGET_VERSION
    const { download } = createDownload(() => ({ success: true, content: NEW_BINARY }))

    const outcome = await syncRuntimeBinary(syncOptions({ download }))

    expect(outcome).toEqual({ status: 'current', target: TARGET })
    expect(download).not.toHaveBeenCalled()
  })

  it('文件字节被动过但版本没变时同样判为已一致，不会每次启动都重下', async () => {
    installedVersion = TARGET_VERSION
    // 重签名之类的后处理会改字节，此时文件哈希与发布资产必然不同。
    fs.writeFileSync(runtimePath, `${NEW_BINARY}-resigned`, 'utf8')
    const { download } = createDownload(() => ({ success: true, content: NEW_BINARY }))

    const outcome = await syncRuntimeBinary(syncOptions({ download }))

    expect(outcome.status).toBe('current')
    expect(outcome.target).toEqual(TARGET)
    expect(download).not.toHaveBeenCalled()
  })

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

  it('装的是比线上最新旧的一版：下载并替换成线上最新', async () => {
    installedVersion = INSTALLED_VERSION
    const { download, urls } = createDownload(() => ({ success: true, content: NEW_BINARY }))

    const outcome = await syncRuntimeBinary(syncOptions({ download }))

    expect(outcome.status).toBe('upgraded')
    expect(outcome.target).toEqual(TARGET)
    expect(urls).toEqual([buildRuntimeBinarySources(TARGET_VERSION)[0].url])
    expect(fs.readFileSync(runtimePath, 'utf8')).toBe(NEW_BINARY)
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

  it('版本问不出来时按需要更换处理', async () => {
    installedVersion = null
    const { download } = createDownload(() => ({ success: true, content: NEW_BINARY }))

    const outcome = await syncRuntimeBinary(syncOptions({ download }))

    expect(outcome.status).toBe('upgraded')
    expect(fs.readFileSync(runtimePath, 'utf8')).toBe(NEW_BINARY)
  })

  it.each(['dev', 'nightly'])('自报版本不合法（%s）时同样按需要更换处理', async version => {
    // 开发者本地构建自报 `dev`：不能当成「本地更高」放过，否则会一直不更新。
    installedVersion = version
    const { download } = createDownload(() => ({ success: true, content: NEW_BINARY }))

    const outcome = await syncRuntimeBinary(syncOptions({ download }))

    expect(outcome.status).toBe('upgraded')
    expect(fs.readFileSync(runtimePath, 'utf8')).toBe(NEW_BINARY)
  })

  it('替换成功后不留下临时文件与让路用的旧文件', async () => {
    const { download } = createDownload(() => ({ success: true, content: NEW_BINARY }))

    await syncRuntimeBinary(syncOptions({ download }))

    expect(installDir()).toEqual(['auto-mas-runtime.exe'])
  })

  it('exe 下载失败时换下一个源', async () => {
    const stub = createDownload(url =>
      isGithubUrl(url)
        ? { success: true, content: NEW_BINARY }
        : { success: false, error: 'HTTP 502' }
    )

    const outcome = await syncRuntimeBinary(syncOptions({ download: stub.download }))

    expect(outcome.status).toBe('upgraded')
    // CNB 与三个 gh-proxy 家族的源全试过，最后落到官方源。
    expect(stub.urls).toHaveLength(5)
    expect(isGithubUrl(stub.urls.at(-1) ?? '')).toBe(true)
    expect(fs.readFileSync(runtimePath, 'utf8')).toBe(NEW_BINARY)
  })

  it('下到的 exe 与可信清单里的哈希不符时判该源失败并换下一个', async () => {
    const stub = createDownload(url =>
      isGithubUrl(url)
        ? { success: true, content: NEW_BINARY }
        : { success: true, content: '<html>404 from proxy</html>' }
    )

    const outcome = await syncRuntimeBinary(syncOptions({ download: stub.download }))

    expect(outcome.status).toBe('upgraded')
    expect(stub.urls).toHaveLength(5)
    expect(fs.readFileSync(runtimePath, 'utf8')).toBe(NEW_BINARY)
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

  it('CNB 的清单取不到时用 GitHub 的清单，exe 仍按顺序从第一个能下的源取', async () => {
    const sums = createSums(url =>
      isCnbUrl(url)
        ? { kind: 'failed', error: 'ECONNRESET' }
        : { kind: 'text', text: sumsFor(NEW_BINARY) }
    )
    const stub = createDownload(() => ({ success: true, content: NEW_BINARY }))

    const outcome = await syncRuntimeBinary(
      syncOptions({ download: stub.download, fetchText: sums.fetchText })
    )

    expect(outcome.status).toBe('upgraded')
    expect(stub.urls).toEqual([buildRuntimeBinarySources(TARGET_VERSION)[0].url])
    expect(fs.readFileSync(runtimePath, 'utf8')).toBe(NEW_BINARY)
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

  it('所有 exe 源都失败时保留原有 exe，失败原因是一句能照着做的话', async () => {
    const stub = createDownload(() => ({ success: false, error: '连接超时' }))

    const outcome = await syncRuntimeBinary(syncOptions({ download: stub.download }))

    expect(outcome.status).toBe('failed')
    expect(outcome.code).toBe(RUNTIME_BINARY_DOWNLOAD_FAILED)
    expect(outcome.error).toContain('连接超时')
    // 给人看的部分：先检查网络，实在不行手动下载 CNB 那份放到安装目录。
    expect(outcome.error).toContain('请检查网络后重试')
    expect(outcome.error).toContain(buildRuntimeBinarySources(TARGET_VERSION)[0].url)
    expect(outcome.error).toContain(path.dirname(runtimePath))
    expect(stub.urls).toHaveLength(5)
    expect(fs.readFileSync(runtimePath, 'utf8')).toBe(OLD_BINARY)
    expect(installDir()).toEqual(['auto-mas-runtime.exe'])
  })

  it('时间预算用完后不再开新的下载源，并保留原有 exe', async () => {
    const { download, urls } = createDownload(() => ({ success: true, content: NEW_BINARY }))

    const outcome = await syncRuntimeBinary(syncOptions({ download, budgetMs: 0 }))

    expect(outcome.status).toBe('failed')
    expect(outcome.code).toBe(RUNTIME_BINARY_DOWNLOAD_FAILED)
    expect(outcome.error).toContain('时间预算')
    expect(urls).toHaveLength(0)
    expect(fs.readFileSync(runtimePath, 'utf8')).toBe(OLD_BINARY)
  })

  it('AUTO_MAS_RUNTIME_EXE 指定的 Runtime 不被覆盖', async () => {
    process.env[RUNTIME_EXE_ENV] = runtimePath
    const { download } = createDownload(() => ({ success: true, content: NEW_BINARY }))

    const outcome = await syncRuntimeBinary(syncOptions({ download }))

    expect(outcome.status).toBe('skipped')
    expect(readVersion).not.toHaveBeenCalled()
    expect(download).not.toHaveBeenCalled()
    expect(fs.readFileSync(runtimePath, 'utf8')).toBe(OLD_BINARY)
  })

  it('exe 不存在时也能装上线上最新版', async () => {
    installedVersion = null
    fs.rmSync(runtimePath)
    const { download } = createDownload(() => ({ success: true, content: NEW_BINARY }))

    const outcome = await syncRuntimeBinary(syncOptions({ download }))

    expect(outcome.status).toBe('upgraded')
    expect(fs.readFileSync(runtimePath, 'utf8')).toBe(NEW_BINARY)
  })

  it('上次中断留下的临时文件不会被当成结果，exe 能跑时旧备份一并清掉', async () => {
    fs.writeFileSync(`${runtimePath}.download`, '半截文件', 'utf8')
    fs.writeFileSync(`${runtimePath}.download-abc-1`, '上次超时放弃的半截文件', 'utf8')
    fs.writeFileSync(`${runtimePath}.old`, '上次让路的旧文件', 'utf8')
    const { download } = createDownload(() => ({ success: true, content: NEW_BINARY }))

    const outcome = await syncRuntimeBinary(syncOptions({ download }))

    expect(outcome.status).toBe('upgraded')
    expect(fs.readFileSync(runtimePath, 'utf8')).toBe(NEW_BINARY)
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

    it('在途的是另一个版本时，等它结束后再按本次目标核对一次，不拿它的结果冒充', async () => {
      const OTHER_VERSION = 'v0.1.9'
      const OTHER_BINARY = 'other-runtime-binary'
      let finishOther: (() => void) | undefined
      const download = vi.fn(
        (url: string, savePath: string) =>
          new Promise<{ success: boolean }>(resolve => {
            const write = () => {
              fs.writeFileSync(
                savePath,
                url.includes(OTHER_VERSION) ? OTHER_BINARY : NEW_BINARY,
                'utf8'
              )
              resolve({ success: true })
            }
            if (url.includes(OTHER_VERSION)) {
              finishOther = write
            } else {
              write()
            }
          })
      )
      const { fetchText } = createSums(url =>
        url.includes(OTHER_VERSION)
          ? { kind: 'text', text: sumsFor(OTHER_BINARY, runtimeAssetName(OTHER_VERSION)) }
          : { kind: 'text', text: sumsFor(NEW_BINARY) }
      )
      // 另一版换上后自报 v0.1.9，本次要的是 v0.1.5：只升不降，第二次核对后保留本地。
      const versionOf = vi.fn(async (target: string) => {
        const content = fs.readFileSync(target, 'utf8')
        if (content === OTHER_BINARY) return OTHER_VERSION
        if (content === NEW_BINARY) return TARGET_VERSION
        return INSTALLED_VERSION
      })

      const first = syncRuntimeBinary(
        syncOptions({
          download,
          fetchText,
          readVersion: versionOf,
          target: { version: OTHER_VERSION },
        })
      )
      const second = syncRuntimeBinary(syncOptions({ download, fetchText, readVersion: versionOf }))
      await vi.waitFor(() => expect(finishOther).toBeDefined())
      finishOther?.()

      const [firstOutcome, secondOutcome] = await Promise.all([first, second])

      expect(firstOutcome).toMatchObject({ status: 'upgraded', target: { version: OTHER_VERSION } })
      // 后来者没有被前一次的结果冒充：它按本次目标重新核对，发现本地更高就保留。
      expect(secondOutcome).toMatchObject({ status: 'current', target: TARGET })
      expect(download).toHaveBeenCalledTimes(1)
      expect(fs.readFileSync(runtimePath, 'utf8')).toBe(OTHER_BINARY)
    })

    it('上一次结束后再调用会重新核对，而不是复用旧结果', async () => {
      const { download } = createDownload(() => ({ success: true, content: NEW_BINARY }))

      const first = await syncRuntimeBinary(syncOptions({ download }))
      const second = await syncRuntimeBinary(syncOptions({ download }))

      expect(first.status).toBe('upgraded')
      // 第二轮问到的已经是换上去的那份，判已一致，不再下载。
      expect(second.status).toBe('current')
      expect(download).toHaveBeenCalledTimes(1)
    })
  })

  describe('慢源上限', () => {
    /** 前 `stallCount` 个 exe 源永远不结束，直到测试自己放行；其余请求立刻成功。 */
    function createStallingDownload(stallCount = 1) {
      const sources = buildRuntimeBinarySources(TARGET_VERSION)
      const urls: string[] = []
      let releaseStalled: (() => void) | undefined
      const stalled = new Promise<void>(resolve => {
        releaseStalled = resolve
      })
      const download = vi.fn(
        async (url: string, savePath: string, onProgress?: (p: { progress: number }) => void) => {
          urls.push(url)
          const sourceIndex = sources.findIndex(source => source.url === url)
          if (sourceIndex < stallCount) {
            await stalled
            // 放弃之后才写进来的内容不能影响任何东西。
            onProgress?.({ progress: 99 })
            fs.writeFileSync(savePath, '<html>late garbage</html>', 'utf8')
            return { success: true }
          }
          fs.writeFileSync(savePath, NEW_BINARY, 'utf8')
          return { success: true }
        }
      )
      return { download, urls, release: () => releaseStalled?.() }
    }

    it('单个源超过时长上限就换下一个源', async () => {
      const stub = createStallingDownload()
      const progress: RuntimeBinarySyncProgress[] = []

      const outcome = await syncRuntimeBinary(
        syncOptions({
          download: stub.download,
          sourceTimeoutMs: 20,
          onProgress: update => progress.push(update),
        })
      )

      expect(outcome.status).toBe('upgraded')
      expect(stub.urls).toHaveLength(2)
      expect(fs.readFileSync(runtimePath, 'utf8')).toBe(NEW_BINARY)

      // 被放弃的那次下载最终写完时：不动 exe，不再上报进度，临时文件被清掉。
      stub.release()
      await vi.waitFor(() => expect(installDir()).toEqual(['auto-mas-runtime.exe']))
      expect(fs.readFileSync(runtimePath, 'utf8')).toBe(NEW_BINARY)
      expect(progress.some(update => update.progress === 99)).toBe(false)
    })

    it('一个可信来源的清单停滞时用另一个的，不等它', async () => {
      const never = new Promise<RuntimeTextFetchOutcome>(() => {})
      const fetchText = vi.fn((url: string) =>
        isCnbUrl(url)
          ? never
          : Promise.resolve<RuntimeTextFetchOutcome>({ kind: 'text', text: sumsFor(NEW_BINARY) })
      )
      const { download } = createDownload(() => ({ success: true, content: NEW_BINARY }))
      const startedAt = Date.now()

      const outcome = await syncRuntimeBinary(syncOptions({ download, fetchText }))

      expect(Date.now() - startedAt).toBeLessThan(2000)
      expect(outcome.status).toBe('upgraded')
    })

    it('单源上限不超过本轮剩余预算', async () => {
      // 所有源都停滞：定时器相对 Date.now() 可能早触发约 1ms，此时预算还剩一点，实现会以那
      // 一点为上限再试下一个源，这是对的；用例只断言不会等满 60 秒的单源上限。
      const stub = createStallingDownload(Infinity)
      const startedAt = Date.now()

      const outcome = await syncRuntimeBinary(
        syncOptions({ download: stub.download, budgetMs: 30, sourceTimeoutMs: 60 * 1000 })
      )

      expect(Date.now() - startedAt).toBeLessThan(2000)
      expect(outcome.status).toBe('failed')
      expect(outcome.code).toBe(RUNTIME_BINARY_DOWNLOAD_FAILED)
      expect(outcome.error).toContain('放弃该源')
      expect(stub.urls.length).toBeGreaterThanOrEqual(1)
      expect(fs.readFileSync(runtimePath, 'utf8')).toBe(OLD_BINARY)
      stub.release()
    })
  })

  describe('取消', () => {
    it('版本一致时不看取消判据，直接判已一致', async () => {
      installedVersion = TARGET_VERSION
      const { download } = createDownload(() => ({ success: true, content: NEW_BINARY }))

      const outcome = await syncRuntimeBinary(syncOptions({ download, isCancelled: () => true }))

      expect(outcome.status).toBe('current')
      expect(download).not.toHaveBeenCalled()
    })

    it('下载还没开始就取消：不开任何下载，exe 保持原样', async () => {
      const { download } = createDownload(() => ({ success: true, content: NEW_BINARY }))

      const outcome = await syncRuntimeBinary(syncOptions({ download, isCancelled: () => true }))

      expect(outcome.status).toBe('cancelled')
      expect(outcome.code).toBe(RUNTIME_BINARY_CANCELLED)
      expect(download).not.toHaveBeenCalled()
      expect(fs.readFileSync(runtimePath, 'utf8')).toBe(OLD_BINARY)
    })

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

    it('校验通过后才发现已取消：不替换，下载物删掉', async () => {
      let cancelled = false
      const { download } = createDownload(() => {
        cancelled = true
        return { success: true, content: NEW_BINARY }
      })

      const outcome = await syncRuntimeBinary(
        syncOptions({ download, isCancelled: () => cancelled })
      )

      expect(outcome.status).toBe('cancelled')
      expect(fs.readFileSync(runtimePath, 'utf8')).toBe(OLD_BINARY)
      expect(installDir()).toEqual(['auto-mas-runtime.exe'])
    })
  })

  describe('替换与备份', () => {
    const busyError = () =>
      Object.assign(new Error('EBUSY: resource busy or locked'), { code: 'EBUSY' })

    const isMoveIn = (from: string, to: string) => to === runtimePath && from.includes('.download')
    const isRestore = (from: string, to: string) =>
      from === `${runtimePath}.old` && to === runtimePath

    it('总是先把旧文件改名让路，新文件确认能跑之后才清掉备份', async () => {
      const { download } = createDownload(() => ({ success: true, content: NEW_BINARY }))

      const outcome = await syncRuntimeBinary(syncOptions({ download }))

      expect(outcome.status).toBe('upgraded')
      expect(fs.readFileSync(runtimePath, 'utf8')).toBe(NEW_BINARY)
      expect(installDir()).toEqual(['auto-mas-runtime.exe'])
      // 让路：旧 exe 先改名成 .old，再把新文件挪过来。
      expect(renameHook.calls).toEqual([
        [runtimePath, `${runtimePath}.old`],
        [expect.stringContaining('.download'), runtimePath],
      ])
      // 替换前问一次版本、替换后确认一次。
      expect(readVersion).toHaveBeenCalledTimes(2)
    })

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

    it('下载到的 exe 自报版本与目标版本不一致：按失败处理并还原旧文件', async () => {
      // Release 资产自报的版本和 tag 对不上：文件哈希没错，但装上去「是否最新」永远不成立。
      newBinaryVersion = 'v0.9.9'
      const { download } = createDownload(() => ({ success: true, content: NEW_BINARY }))

      const outcome = await syncRuntimeBinary(syncOptions({ download }))

      expect(outcome.status).toBe('failed')
      expect(outcome.code).toBe(RUNTIME_BINARY_REPLACE_FAILED)
      expect(outcome.error).toContain('自报版本为 v0.9.9')
      expect(outcome.error).toContain(`与线上最新 ${TARGET_VERSION} 不一致`)
      expect(outcome.error).toContain('已恢复原来的文件')
      // 不匹配的新文件不能成为最终状态。
      expect(fs.readFileSync(runtimePath, 'utf8')).toBe(OLD_BINARY)
      expect(fs.existsSync(`${runtimePath}.old`)).toBe(false)
      expect(installDir()).toEqual(['auto-mas-runtime.exe'])
    })

    it('新文件跑不起来又被占用换不回去：备份留在 .old，提示下次启动会换回', async () => {
      newBinaryVersion = null
      const newInPlace = () => {
        try {
          return fs.readFileSync(runtimePath, 'utf8') === NEW_BINARY
        } catch {
          return false
        }
      }
      rmHook.before = target => {
        if (target === runtimePath && newInPlace()) throw busyError()
      }
      renameHook.before = (from, to) => {
        if (isRestore(from, to) && newInPlace()) throw busyError()
      }
      const { download } = createDownload(() => ({ success: true, content: NEW_BINARY }))

      const outcome = await syncRuntimeBinary(syncOptions({ download }))

      expect(outcome.status).toBe('failed')
      expect(outcome.code).toBe(RUNTIME_BINARY_REPLACE_FAILED)
      expect(outcome.error).toContain(`仍保留在 ${runtimePath}.old`)
      expect(fs.readFileSync(runtimePath, 'utf8')).toBe(NEW_BINARY)
      expect(fs.readFileSync(`${runtimePath}.old`, 'utf8')).toBe(OLD_BINARY)
    })

    it('原来就没有 exe、新文件又跑不起来时报失败但保留新文件', async () => {
      installedVersion = null
      newBinaryVersion = null
      fs.rmSync(runtimePath)
      const { download } = createDownload(() => ({ success: true, content: NEW_BINARY }))

      const outcome = await syncRuntimeBinary(syncOptions({ download }))

      expect(outcome.status).toBe('failed')
      expect(outcome.code).toBe(RUNTIME_BINARY_REPLACE_FAILED)
      expect(outcome.error).toContain('本机没有可回退的旧版本')
      expect(fs.readFileSync(runtimePath, 'utf8')).toBe(NEW_BINARY)
    })

    it('新文件挪不进去、旧文件也改不回去时保留 .old，下一次同步先把它恢复', async () => {
      const { download } = createDownload(() => ({ success: true, content: NEW_BINARY }))
      renameHook.before = (from, to) => {
        if (isMoveIn(from, to) || isRestore(from, to)) throw busyError()
      }

      const first = await syncRuntimeBinary(syncOptions({ download }))

      expect(first.status).toBe('failed')
      expect(first.code).toBe(RUNTIME_BINARY_REPLACE_FAILED)
      // 正式 exe 不在了，但备份还在，没有被当残留清掉。
      expect(fs.existsSync(runtimePath)).toBe(false)
      expect(fs.readFileSync(`${runtimePath}.old`, 'utf8')).toBe(OLD_BINARY)

      renameHook.before = null
      const second = await syncRuntimeBinary(syncOptions({ download }))

      expect(second.status).toBe('upgraded')
      expect(fs.readFileSync(runtimePath, 'utf8')).toBe(NEW_BINARY)
      expect(installDir()).toEqual(['auto-mas-runtime.exe'])
      // 第二轮开头先把 .old 改回 exe，再照常替换。
      expect(renameHook.calls.filter(([from, to]) => isRestore(from, to))).toHaveLength(2)
    })

    it('exe 自报版本与目标一致时才清陈旧备份', async () => {
      fs.writeFileSync(`${runtimePath}.old`, '上次留下的备份', 'utf8')
      installedVersion = TARGET_VERSION
      const { download } = createDownload(() => ({ success: true, content: NEW_BINARY }))

      const outcome = await syncRuntimeBinary(syncOptions({ download }))

      expect(outcome.status).toBe('current')
      expect(fs.readFileSync(runtimePath, 'utf8')).toBe(OLD_BINARY)
      expect(installDir()).toEqual(['auto-mas-runtime.exe'])
    })

    it('exe 跑不起来而备份还在：先把备份换回来，再照常更新', async () => {
      // 上次换上的新文件跑不起来、换回去又没成功留下的现场：坏的在正式路径，好的在 .old。
      fs.writeFileSync(runtimePath, 'broken-runtime-binary', 'utf8')
      fs.writeFileSync(`${runtimePath}.old`, OLD_BINARY, 'utf8')
      const versionOf = vi.fn(async (target: string) => {
        const content = fs.readFileSync(target, 'utf8')
        if (content === OLD_BINARY) return INSTALLED_VERSION
        if (content === NEW_BINARY) return TARGET_VERSION
        return null
      })
      const { download } = createDownload(() => ({ success: true, content: NEW_BINARY }))

      const outcome = await syncRuntimeBinary(syncOptions({ download, readVersion: versionOf }))

      expect(outcome.status).toBe('upgraded')
      expect(fs.readFileSync(runtimePath, 'utf8')).toBe(NEW_BINARY)
      expect(installDir()).toEqual(['auto-mas-runtime.exe'])
      // 顺序：先 .old → exe（恢复），再 exe → .old（让路），最后新文件挪进来。
      expect(renameHook.calls).toEqual([
        [`${runtimePath}.old`, runtimePath],
        [runtimePath, `${runtimePath}.old`],
        [expect.stringContaining('.download'), runtimePath],
      ])
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

// ==================== 哈希 ====================

describe('hashFileSha256', () => {
  it('算出文件的 SHA-256', async () => {
    await expect(hashFileSha256(runtimePath)).resolves.toBe(sha256(OLD_BINARY))
  })

  it('文件不存在时返回 null 而不是抛错', async () => {
    await expect(hashFileSha256(path.join(workspace, '不存在.exe'))).resolves.toBeNull()
  })
})

// ==================== 第 0 步：对齐线上最新版 ====================

describe('alignRuntimeBinaryWithLatest', () => {
  function alignOptions(
    lookup: LatestRuntimeVersionLookup,
    extra: Partial<RuntimeBinaryAlignOptions> = {}
  ) {
    const fetchLatest = vi.fn(
      async (_channel: string): Promise<LatestRuntimeVersionLookup> => lookup
    )
    const sync = vi.fn(
      async (options: RuntimeBinarySyncOptions): Promise<RuntimeBinarySyncResult> => ({
        status: 'upgraded',
        target: options.target,
      })
    )
    const options: RuntimeBinaryAlignOptions = {
      runtimePath,
      appRoot: workspace,
      channel: 'stable',
      fetchLatest,
      sync,
      ...extra,
    }
    return { fetchLatest, sync, options }
  }

  it('解析线上最新版后按目标版本同步 exe，结果带上目标与来源', async () => {
    const { fetchLatest, sync, options } = alignOptions({
      status: 'resolved',
      version: TARGET_VERSION,
      source: 'cnb',
    })
    const progress: RuntimeBinarySyncProgress[] = []

    const result = await alignRuntimeBinaryWithLatest({
      ...options,
      onProgress: update => progress.push(update),
    })

    expect(fetchLatest).toHaveBeenCalledWith('stable')
    expect(sync).toHaveBeenCalledTimes(1)
    expect(sync.mock.calls[0][0]).toMatchObject({
      runtimePath,
      appRoot: workspace,
      target: TARGET,
    })
    expect(result).toEqual({ status: 'upgraded', target: TARGET, targetSource: 'cnb' })
    expect(progress[0]).toEqual({ progress: 0, message: '正在获取线上最新的 Runtime 版本' })
  })

  it('同步结果为 current 时原样带回，并附上目标来源', async () => {
    const { options } = alignOptions({
      status: 'resolved',
      version: TARGET_VERSION,
      source: 'github',
    })
    const currentSync = vi.fn(
      async (syncOptions: RuntimeBinarySyncOptions): Promise<RuntimeBinarySyncResult> => ({
        status: 'current',
        target: syncOptions.target,
      })
    )

    const result = await alignRuntimeBinaryWithLatest({ ...options, sync: currentSync })

    expect(result).toEqual({ status: 'current', target: TARGET, targetSource: 'github' })
    expect(currentSync).toHaveBeenCalledWith(expect.objectContaining({ target: TARGET }))
  })

  it('AUTO_MAS_RUNTIME_EXE 指定的 Runtime 连最新版本都不解析', async () => {
    process.env[RUNTIME_EXE_ENV] = runtimePath
    const { fetchLatest, sync, options } = alignOptions({
      status: 'resolved',
      version: TARGET_VERSION,
      source: 'cnb',
    })

    await expect(alignRuntimeBinaryWithLatest(options)).resolves.toEqual({ status: 'skipped' })
    expect(fetchLatest).not.toHaveBeenCalled()
    expect(sync).not.toHaveBeenCalled()
  })

  it('解析到最新版之后已被取消时不再同步', async () => {
    const { fetchLatest, sync, options } = alignOptions(
      { status: 'resolved', version: TARGET_VERSION, source: 'github' },
      { isCancelled: () => true }
    )

    const result = await alignRuntimeBinaryWithLatest(options)

    expect(result).toEqual({
      status: 'cancelled',
      target: TARGET,
      targetSource: 'github',
      code: RUNTIME_BINARY_CANCELLED,
    })
    expect(fetchLatest).toHaveBeenCalledTimes(1)
    expect(sync).not.toHaveBeenCalled()
  })

  it('解析不到线上最新版时按失败返回，原因是一句能照着做的话，网络不可用标记原样带回', async () => {
    const { fetchLatest, sync, options } = alignOptions({
      status: 'unavailable',
      error: 'CNB: 15 秒内没有响应；GitHub: ECONNREFUSED',
      networkUnavailable: true,
    })

    const result = await alignRuntimeBinaryWithLatest(options)

    expect(result.status).toBe('failed')
    expect(result.code).toBe(RUNTIME_LATEST_UNAVAILABLE)
    expect(result.networkUnavailable).toBe(true)
    expect(result.target).toBeUndefined()
    expect(result.error).toContain('请检查网络后重试')
    expect(result.error).toContain('ECONNREFUSED')
    expect(fetchLatest).toHaveBeenCalledTimes(1)
    expect(sync).not.toHaveBeenCalled()
  })

  it('同步失败的原因与结果码原样带回', async () => {
    const { options } = alignOptions({
      status: 'resolved',
      version: TARGET_VERSION,
      source: 'cnb',
    })
    const sync = vi.fn(
      async (syncOptions: RuntimeBinarySyncOptions): Promise<RuntimeBinarySyncResult> => ({
        status: 'failed',
        target: syncOptions.target,
        error: `没能下载到线上最新的 Runtime ${TARGET_VERSION}（…）。请检查网络后重试`,
        code: RUNTIME_BINARY_DOWNLOAD_FAILED,
      })
    )

    const result = await alignRuntimeBinaryWithLatest({ ...options, sync })

    expect(result).toMatchObject({
      status: 'failed',
      code: RUNTIME_BINARY_DOWNLOAD_FAILED,
      target: TARGET,
      targetSource: 'cnb',
    })
    expect(result.error).toContain('请检查网络后重试')
  })

  it('默认实现真的走 syncRuntimeBinary：目标版本与 exe 一致时判已一致', async () => {
    installedVersion = TARGET_VERSION
    const fetchLatest = vi.fn(async (): Promise<LatestRuntimeVersionLookup> => ({
      status: 'resolved',
      version: TARGET_VERSION,
      source: 'cnb',
    }))

    const result = await alignRuntimeBinaryWithLatest({
      runtimePath,
      appRoot: workspace,
      channel: 'stable',
      fetchLatest,
      // 对齐本身不暴露 readVersion；这里通过 sync 包装把它注入真实同步实现，exe 仍是测试目录里的文本文件。
      sync: options => syncRuntimeBinary({ ...options, readVersion }),
    })

    expect(result).toEqual({ status: 'current', target: TARGET, targetSource: 'cnb' })
    expect(readVersion).toHaveBeenCalledTimes(1)
  })
})
