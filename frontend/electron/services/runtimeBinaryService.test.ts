import * as crypto from 'crypto'
import * as fs from 'fs'
import * as os from 'os'
import * as path from 'path'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { RUNTIME_EXE_ENV } from './runtime'
import {
  RUNTIME_BINARY_DOWNLOAD_FAILED,
  RUNTIME_BINARY_REPLACE_FAILED,
  RUNTIME_PIN_RELATIVE_PATH,
  buildRuntimeBinarySources,
  hashFileSha256,
  parseRuntimeSums,
  readRuntimeBinaryPin,
  runtimeAssetName,
  syncRuntimeBinary,
  type RuntimeBinarySyncOptions,
  type RuntimeBinarySyncProgress,
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
vi.mock('fs', async importOriginal => {
  const actual = await importOriginal<typeof import('fs')>()
  return {
    ...actual,
    renameSync: (from: fs.PathLike, to: fs.PathLike) => {
      renameHook.calls.push([String(from), String(to)])
      renameHook.before?.(String(from), String(to))
      return actual.renameSync(from, to)
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
const PINNED_VERSION = 'v0.1.5'

function sha256(content: string): string {
  return crypto.createHash('sha256').update(content).digest('hex')
}

const PINNED_ASSET = runtimeAssetName(PINNED_VERSION)

/** 照着真实 Release 的 `SHA256SUMS.txt` 造：`<hash>  <asset>`，CRLF 结尾。 */
function sumsFor(content: string, asset = PINNED_ASSET): string {
  return `${sha256(content)}  ${asset}\r\n`
}

const isSumsUrl = (url: string) => url.endsWith('/SHA256SUMS.txt')

/** 每个用例一套独立的安装目录与受管源码目录。 */
let workspace: string
let runtimePath: string
let sourceRoot: string
/** 磁盘上那个 exe 自报的版本，用例按需改写。 */
let installedVersion: string | null

/** 写钉扎文件；传版本号时照 CI 提交的样子加一个换行，传其他文本时原样写入。 */
function writePin(text: string, raw = false): void {
  const pinPath = path.join(sourceRoot, RUNTIME_PIN_RELATIVE_PATH)
  fs.mkdirSync(path.dirname(pinPath), { recursive: true })
  fs.writeFileSync(pinPath, raw ? text : `${text}\n`, 'utf8')
}

type DownloadPlan = (url: string) => { success: boolean; content?: string; error?: string }

/**
 * 造一个「写入指定内容」的下载器桩，并记录被请求过的 URL。
 *
 * `plan` 只管 exe；每个源的 `SHA256SUMS.txt` 缺省按 NEW_BINARY 的哈希照真实格式返回，
 * 要模拟清单出问题的用例自己传 `sums`。`exeUrls` 只含 exe 请求，方便数「试了几个源」。
 */
function createDownload(
  plan: DownloadPlan,
  sums: DownloadPlan = () => ({ success: true, content: sumsFor(NEW_BINARY) })
) {
  const urls: string[] = []
  const download = vi.fn(
    async (url: string, savePath: string, onProgress?: (p: { progress: number }) => void) => {
      urls.push(url)
      const outcome = isSumsUrl(url) ? sums(url) : plan(url)
      if (!outcome.success) return { success: false, error: outcome.error ?? '下载失败' }
      onProgress?.({ progress: 50 })
      fs.writeFileSync(savePath, outcome.content ?? '', 'utf8')
      return { success: true }
    }
  )
  return {
    download,
    urls,
    get exeUrls() {
      return urls.filter(url => !isSumsUrl(url))
    },
  }
}

/** 版本查询走桩，测试里那个 exe 只是个文本文件，真跑不起来。 */
const readVersion = vi.fn(async () => installedVersion)

function syncOptions(extra: Partial<RuntimeBinarySyncOptions> = {}): RuntimeBinarySyncOptions {
  return { runtimePath, appRoot: workspace, sourceRoot, readVersion, ...extra }
}

beforeEach(() => {
  workspace = fs.mkdtempSync(path.join(os.tmpdir(), 'auto-mas-runtime-binary-'))
  runtimePath = path.join(workspace, 'resources', 'auto-mas-runtime.exe')
  sourceRoot = path.join(workspace, 'repo')
  installedVersion = INSTALLED_VERSION
  readVersion.mockClear()
  fs.mkdirSync(path.dirname(runtimePath), { recursive: true })
  fs.writeFileSync(runtimePath, OLD_BINARY, 'utf8')
  delete process.env[RUNTIME_EXE_ENV]
})

afterEach(() => {
  delete process.env[RUNTIME_EXE_ENV]
  fs.rmSync(workspace, { recursive: true, force: true })
})

// ==================== 钉扎文件 ====================

describe('readRuntimeBinaryPin', () => {
  it('读出一行版本号，忽略前后空白与换行', () => {
    writePin(`  ${PINNED_VERSION}\r\n`, true)

    expect(readRuntimeBinaryPin(sourceRoot)).toEqual({ version: PINNED_VERSION })
  })

  it('接受带预发布后缀的版本号', () => {
    writePin('v0.2.0-beta.1')

    expect(readRuntimeBinaryPin(sourceRoot)).toEqual({ version: 'v0.2.0-beta.1' })
  })

  it('文件不存在时按未钉扎处理', () => {
    expect(readRuntimeBinaryPin(sourceRoot)).toBeNull()
  })

  it.each([
    ['文件为空', ''],
    ['只有空白', ' \r\n\n'],
    ['版本号带路径分隔符', 'v0.1.5/../evil'],
    ['版本号没有 v 前缀', '0.1.5'],
    ['版本号带空白', 'v0.1 .5'],
    ['写了不止一行', `${PINNED_VERSION}\nv0.1.6`],
    ['写成了旧的 JSON 钉扎', JSON.stringify({ version: PINNED_VERSION, sha256: 'a'.repeat(64) })],
  ])('%s 时按未钉扎处理', (_label, text) => {
    writePin(text, true)

    expect(readRuntimeBinaryPin(sourceRoot)).toBeNull()
  })

  it('文件大得离谱时按未钉扎处理', () => {
    writePin(`${PINNED_VERSION}${' '.repeat(64 * 1024)}`, true)

    expect(readRuntimeBinaryPin(sourceRoot)).toBeNull()
  })
})

// ==================== 校验清单 ====================

describe('parseRuntimeSums', () => {
  it('按资产名取出对应行的哈希，容忍 CRLF 与大写', () => {
    const text = `${'A'.repeat(64)}  other.exe\r\n${sha256(NEW_BINARY).toUpperCase()}  ${PINNED_ASSET}\r\n`

    expect(parseRuntimeSums(text, PINNED_ASSET)).toBe(sha256(NEW_BINARY))
  })

  it.each([
    ['清单为空', ''],
    ['清单里没有这个资产', sumsFor(NEW_BINARY, 'auto-mas-runtime-v9.9.9.exe')],
    ['哈希长度不对', `abc123  ${PINNED_ASSET}\n`],
    ['哈希含非十六进制字符', `${'z'.repeat(64)}  ${PINNED_ASSET}\n`],
    ['只有哈希没有文件名', `${sha256(NEW_BINARY)}\n`],
    ['拿到的是错误页', '<html><body>404 Not Found</body></html>'],
  ])('%s 时返回 null', (_label, text) => {
    expect(parseRuntimeSums(text, PINNED_ASSET)).toBeNull()
  })
})

// ==================== 下载源 ====================

describe('buildRuntimeBinarySources', () => {
  it('代理源排在官方源之前，官方源永远兜底在最后', () => {
    const sources = buildRuntimeBinarySources(PINNED_VERSION)

    expect(sources.map(source => source.key)).toEqual([
      'ghproxy_cloudflare',
      'ghproxy_fastly',
      'ghproxy_edgeone',
      'github',
    ])
    expect(sources.at(-1)?.url).toBe(
      'https://github.com/AUTO-MAS-Project/AUTO-MAS-Runtime/releases/download/v0.1.5/auto-mas-runtime-v0.1.5.exe'
    )
    expect(sources.at(-1)?.sumsUrl).toBe(
      'https://github.com/AUTO-MAS-Project/AUTO-MAS-Runtime/releases/download/v0.1.5/SHA256SUMS.txt'
    )
  })

  it('每个源的 exe 与校验清单都指向同一个 Release', () => {
    for (const source of buildRuntimeBinarySources(PINNED_VERSION)) {
      const release = source.url.slice(0, -`/${PINNED_ASSET}`.length)
      expect(release.endsWith(`/releases/download/${PINNED_VERSION}`)).toBe(true)
      expect(source.sumsUrl).toBe(`${release}/SHA256SUMS.txt`)
    }
  })
})

// ==================== 同步 ====================

describe('syncRuntimeBinary', () => {
  it('本体没带钉扎文件时连版本都不问', async () => {
    const { download } = createDownload(() => ({ success: true, content: NEW_BINARY }))

    const outcome = await syncRuntimeBinary(syncOptions({ download }))

    expect(outcome.status).toBe('unpinned')
    expect(readVersion).not.toHaveBeenCalled()
    expect(download).not.toHaveBeenCalled()
    expect(fs.readFileSync(runtimePath, 'utf8')).toBe(OLD_BINARY)
  })

  it('exe 自报的版本就是钉扎那一版时不下载', async () => {
    writePin(PINNED_VERSION)
    installedVersion = PINNED_VERSION
    const { download } = createDownload(() => ({ success: true, content: NEW_BINARY }))

    const outcome = await syncRuntimeBinary(syncOptions({ download }))

    expect(outcome.status).toBe('current')
    expect(download).not.toHaveBeenCalled()
  })

  it('文件字节被动过但版本没变时同样判为已一致，不会每次启动都重下', async () => {
    writePin(PINNED_VERSION)
    installedVersion = PINNED_VERSION
    // 重签名之类的后处理会改字节，此时文件哈希与发布资产必然不同。
    fs.writeFileSync(runtimePath, `${NEW_BINARY}-resigned`, 'utf8')
    const { download } = createDownload(() => ({ success: true, content: NEW_BINARY }))

    const outcome = await syncRuntimeBinary(syncOptions({ download }))

    expect(outcome.status).toBe('current')
    expect(download).not.toHaveBeenCalled()
  })

  it('版本不一致时下载钉扎版本并原地替换', async () => {
    writePin(PINNED_VERSION)
    const { download, urls } = createDownload(() => ({ success: true, content: NEW_BINARY }))
    const progress: RuntimeBinarySyncProgress[] = []

    const outcome = await syncRuntimeBinary(
      syncOptions({ download, onProgress: update => progress.push(update) })
    )

    expect(outcome.status).toBe('upgraded')
    expect(outcome.pin).toEqual({ version: PINNED_VERSION })
    // 第一个源就成功，不该继续往下试：先取它的清单，再取它的 exe。
    const [first] = buildRuntimeBinarySources(PINNED_VERSION)
    expect(urls).toEqual([first.sumsUrl, first.url])
    expect(fs.readFileSync(runtimePath, 'utf8')).toBe(NEW_BINARY)
    expect(progress.at(-1)).toEqual({
      progress: 100,
      message: `Runtime 已更新到 ${PINNED_VERSION}`,
    })
  })

  it('版本问不出来时按需要更换处理', async () => {
    writePin(PINNED_VERSION)
    installedVersion = null
    const { download } = createDownload(() => ({ success: true, content: NEW_BINARY }))

    const outcome = await syncRuntimeBinary(syncOptions({ download }))

    expect(outcome.status).toBe('upgraded')
    expect(fs.readFileSync(runtimePath, 'utf8')).toBe(NEW_BINARY)
  })

  it('本体回退时 Runtime 跟着退回旧版本', async () => {
    writePin(PINNED_VERSION)
    // 装的是比钉扎更新的一版，同样要换回钉扎那版。
    installedVersion = 'v0.9.0'
    const { download } = createDownload(() => ({ success: true, content: NEW_BINARY }))

    const outcome = await syncRuntimeBinary(syncOptions({ download }))

    expect(outcome.status).toBe('upgraded')
    expect(fs.readFileSync(runtimePath, 'utf8')).toBe(NEW_BINARY)
  })

  it('替换成功后不留下临时文件与让路用的旧文件', async () => {
    writePin(PINNED_VERSION)
    const { download } = createDownload(() => ({ success: true, content: NEW_BINARY }))

    await syncRuntimeBinary(syncOptions({ download }))

    expect(fs.readdirSync(path.dirname(runtimePath))).toEqual(['auto-mas-runtime.exe'])
  })

  it('下载失败时换下一个源', async () => {
    writePin(PINNED_VERSION)
    const stub = createDownload(url =>
      url.includes('gh-proxy.com')
        ? { success: false, error: 'HTTP 502' }
        : { success: true, content: NEW_BINARY }
    )

    const outcome = await syncRuntimeBinary(syncOptions({ download: stub.download }))

    expect(outcome.status).toBe('upgraded')
    // 三个 gh-proxy 家族的源全试过，最后落到官方源。
    expect(stub.exeUrls).toHaveLength(4)
    expect(stub.exeUrls.at(-1)?.startsWith('https://github.com/')).toBe(true)
    expect(fs.readFileSync(runtimePath, 'utf8')).toBe(NEW_BINARY)
  })

  it('下到的 exe 与该源清单里的哈希不符时判该源失败并换下一个', async () => {
    writePin(PINNED_VERSION)
    const stub = createDownload(url =>
      url.startsWith('https://github.com/')
        ? { success: true, content: NEW_BINARY }
        : { success: true, content: '<html>404 from proxy</html>' }
    )

    const outcome = await syncRuntimeBinary(syncOptions({ download: stub.download }))

    expect(outcome.status).toBe('upgraded')
    expect(stub.exeUrls).toHaveLength(4)
    expect(fs.readFileSync(runtimePath, 'utf8')).toBe(NEW_BINARY)
    expect(fs.readdirSync(path.dirname(runtimePath))).toEqual(['auto-mas-runtime.exe'])
  })

  it('校验清单取不到时不下 exe，直接换下一个源', async () => {
    writePin(PINNED_VERSION)
    const stub = createDownload(
      () => ({ success: true, content: NEW_BINARY }),
      url =>
        url.startsWith('https://github.com/')
          ? { success: true, content: sumsFor(NEW_BINARY) }
          : { success: false, error: 'HTTP 404' }
    )

    const outcome = await syncRuntimeBinary(syncOptions({ download: stub.download }))

    expect(outcome.status).toBe('upgraded')
    // 前三个源只请求了清单就被放弃，只有官方源走到了 exe。
    expect(stub.urls.filter(isSumsUrl)).toHaveLength(4)
    expect(stub.exeUrls).toEqual([buildRuntimeBinarySources(PINNED_VERSION).at(-1)?.url])
    expect(fs.readFileSync(runtimePath, 'utf8')).toBe(NEW_BINARY)
    expect(fs.readdirSync(path.dirname(runtimePath))).toEqual(['auto-mas-runtime.exe'])
  })

  it('校验清单格式不对（如代理返回错误页）时换下一个源', async () => {
    writePin(PINNED_VERSION)
    const stub = createDownload(
      () => ({ success: true, content: NEW_BINARY }),
      url =>
        url.startsWith('https://github.com/')
          ? { success: true, content: sumsFor(NEW_BINARY) }
          : { success: true, content: '<html>403 Forbidden</html>' }
    )

    const outcome = await syncRuntimeBinary(syncOptions({ download: stub.download }))

    expect(outcome.status).toBe('upgraded')
    expect(stub.exeUrls).toEqual([buildRuntimeBinarySources(PINNED_VERSION).at(-1)?.url])
    expect(fs.readFileSync(runtimePath, 'utf8')).toBe(NEW_BINARY)
    expect(fs.readdirSync(path.dirname(runtimePath))).toEqual(['auto-mas-runtime.exe'])
  })

  it('清单里没有钉扎那一版的资产时换下一个源', async () => {
    writePin(PINNED_VERSION)
    const stub = createDownload(
      () => ({ success: true, content: NEW_BINARY }),
      url =>
        url.startsWith('https://github.com/')
          ? { success: true, content: sumsFor(NEW_BINARY) }
          : { success: true, content: sumsFor(NEW_BINARY, 'auto-mas-runtime-v0.1.4.exe') }
    )

    const outcome = await syncRuntimeBinary(syncOptions({ download: stub.download }))

    expect(outcome.status).toBe('upgraded')
    expect(stub.exeUrls).toEqual([buildRuntimeBinarySources(PINNED_VERSION).at(-1)?.url])
    expect(fs.readFileSync(runtimePath, 'utf8')).toBe(NEW_BINARY)
  })

  it('清单与 exe 都完好但互不对应时判该源失败并换下一个', async () => {
    writePin(PINNED_VERSION)
    // 代理源缓存了旧清单：格式合法、资产名也对，只是哈希是另一份文件的。
    const stub = createDownload(
      () => ({ success: true, content: NEW_BINARY }),
      url =>
        url.startsWith('https://github.com/')
          ? { success: true, content: sumsFor(NEW_BINARY) }
          : { success: true, content: sumsFor('stale-runtime-binary') }
    )

    const outcome = await syncRuntimeBinary(syncOptions({ download: stub.download }))

    expect(outcome.status).toBe('upgraded')
    expect(stub.exeUrls).toHaveLength(4)
    expect(fs.readFileSync(runtimePath, 'utf8')).toBe(NEW_BINARY)
    expect(fs.readdirSync(path.dirname(runtimePath))).toEqual(['auto-mas-runtime.exe'])
  })

  it('所有源都失败时保留原有 exe 并报可继续启动的失败', async () => {
    writePin(PINNED_VERSION)
    const stub = createDownload(() => ({ success: false, error: '连接超时' }))

    const outcome = await syncRuntimeBinary(syncOptions({ download: stub.download }))

    expect(outcome.status).toBe('failed')
    expect(outcome.code).toBe(RUNTIME_BINARY_DOWNLOAD_FAILED)
    expect(outcome.error).toContain('连接超时')
    expect(stub.exeUrls).toHaveLength(4)
    expect(fs.readFileSync(runtimePath, 'utf8')).toBe(OLD_BINARY)
    expect(fs.readdirSync(path.dirname(runtimePath))).toEqual(['auto-mas-runtime.exe'])
  })

  it('所有源的清单都取不到时保留原有 exe，失败原因指向清单', async () => {
    writePin(PINNED_VERSION)
    const stub = createDownload(
      () => ({ success: true, content: NEW_BINARY }),
      () => ({ success: false, error: 'HTTP 404' })
    )

    const outcome = await syncRuntimeBinary(syncOptions({ download: stub.download }))

    expect(outcome.status).toBe('failed')
    expect(outcome.code).toBe(RUNTIME_BINARY_DOWNLOAD_FAILED)
    expect(outcome.error).toContain('校验清单获取失败')
    expect(stub.exeUrls).toHaveLength(0)
    expect(fs.readFileSync(runtimePath, 'utf8')).toBe(OLD_BINARY)
    expect(fs.readdirSync(path.dirname(runtimePath))).toEqual(['auto-mas-runtime.exe'])
  })

  it('时间预算用完后不再开新的下载源，并保留原有 exe', async () => {
    writePin(PINNED_VERSION)
    const { download, urls } = createDownload(() => ({ success: true, content: NEW_BINARY }))

    const outcome = await syncRuntimeBinary(syncOptions({ download, budgetMs: 0 }))

    expect(outcome.status).toBe('failed')
    expect(outcome.code).toBe(RUNTIME_BINARY_DOWNLOAD_FAILED)
    expect(outcome.error).toContain('时间预算')
    expect(urls).toHaveLength(0)
    expect(fs.readFileSync(runtimePath, 'utf8')).toBe(OLD_BINARY)
  })

  it('AUTO_MAS_RUNTIME_EXE 指定的 Runtime 不被覆盖', async () => {
    writePin(PINNED_VERSION)
    process.env[RUNTIME_EXE_ENV] = runtimePath
    const { download } = createDownload(() => ({ success: true, content: NEW_BINARY }))

    const outcome = await syncRuntimeBinary(syncOptions({ download }))

    expect(outcome.status).toBe('skipped')
    expect(readVersion).not.toHaveBeenCalled()
    expect(download).not.toHaveBeenCalled()
    expect(fs.readFileSync(runtimePath, 'utf8')).toBe(OLD_BINARY)
  })

  it('exe 不存在时也能装上钉扎版本', async () => {
    writePin(PINNED_VERSION)
    installedVersion = null
    fs.rmSync(runtimePath)
    const { download } = createDownload(() => ({ success: true, content: NEW_BINARY }))

    const outcome = await syncRuntimeBinary(syncOptions({ download }))

    expect(outcome.status).toBe('upgraded')
    expect(fs.readFileSync(runtimePath, 'utf8')).toBe(NEW_BINARY)
  })

  it('上次中断留下的临时文件不会被当成结果', async () => {
    writePin(PINNED_VERSION)
    fs.writeFileSync(`${runtimePath}.download`, '半截文件', 'utf8')
    fs.writeFileSync(`${runtimePath}.download-abc-1`, '上次超时放弃的半截文件', 'utf8')
    fs.writeFileSync(`${runtimePath}.old`, '上次让路的旧文件', 'utf8')
    const { download } = createDownload(() => ({ success: true, content: NEW_BINARY }))

    const outcome = await syncRuntimeBinary(syncOptions({ download }))

    expect(outcome.status).toBe('upgraded')
    expect(fs.readFileSync(runtimePath, 'utf8')).toBe(NEW_BINARY)
    expect(fs.readdirSync(path.dirname(runtimePath))).toEqual(['auto-mas-runtime.exe'])
  })

  describe('在途互斥', () => {
    it('并发两次同步只下载一次，后来者拿到同一个结果与进度', async () => {
      writePin(PINNED_VERSION)
      let finish: (() => void) | undefined
      const download = vi.fn(
        (url: string, savePath: string, onProgress?: (p: { progress: number }) => void) =>
          new Promise<{ success: boolean }>(resolve => {
            if (isSumsUrl(url)) {
              fs.writeFileSync(savePath, sumsFor(NEW_BINARY), 'utf8')
              resolve({ success: true })
              return
            }
            finish = () => {
              onProgress?.({ progress: 50 })
              fs.writeFileSync(savePath, NEW_BINARY, 'utf8')
              resolve({ success: true })
            }
          })
      )
      const exeDownloads = () => download.mock.calls.filter(([url]) => !isSumsUrl(url)).length
      const firstProgress: RuntimeBinarySyncProgress[] = []
      const secondProgress: RuntimeBinarySyncProgress[] = []

      const first = syncRuntimeBinary(
        syncOptions({ download, onProgress: update => firstProgress.push(update) })
      )
      const second = syncRuntimeBinary(
        syncOptions({ download, onProgress: update => secondProgress.push(update) })
      )
      await vi.waitFor(() => expect(exeDownloads()).toBe(1))
      expect(finish).toBeDefined()
      finish?.()

      const outcomes = await Promise.all([first, second])

      // 一份清单、一份 exe，后来者没有再开任何下载。
      expect(download).toHaveBeenCalledTimes(2)
      expect(exeDownloads()).toBe(1)
      expect(readVersion).toHaveBeenCalledTimes(1)
      expect(outcomes[0]).toBe(outcomes[1])
      expect(outcomes[0].status).toBe('upgraded')
      expect(fs.readFileSync(runtimePath, 'utf8')).toBe(NEW_BINARY)
      expect(secondProgress).toContainEqual({ progress: 50, message: expect.any(String) })
      expect(secondProgress.at(-1)).toEqual(firstProgress.at(-1))
    })

    it('上一次结束后再调用会重新同步', async () => {
      writePin(PINNED_VERSION)
      const { download } = createDownload(() => ({ success: true, content: NEW_BINARY }))

      await syncRuntimeBinary(syncOptions({ download }))
      await syncRuntimeBinary(syncOptions({ download }))

      // 每轮各一份清单加一份 exe。
      expect(download).toHaveBeenCalledTimes(4)
    })
  })

  describe('慢源上限', () => {
    /**
     * 前 `stallCount` 个源的某一类请求（缺省是 exe）永远不结束，直到测试自己放行；
     * 其余请求立刻成功。
     */
    function createStallingDownload(stallCount = 1, stall: 'exe' | 'sums' = 'exe') {
      const sources = buildRuntimeBinarySources(PINNED_VERSION)
      const urls: string[] = []
      let releaseStalled: (() => void) | undefined
      const stalled = new Promise<void>(resolve => {
        releaseStalled = resolve
      })
      const download = vi.fn(
        async (url: string, savePath: string, onProgress?: (p: { progress: number }) => void) => {
          urls.push(url)
          const sourceIndex = sources.findIndex(
            source => source.url === url || source.sumsUrl === url
          )
          const kind = isSumsUrl(url) ? 'sums' : 'exe'
          if (sourceIndex < stallCount && kind === stall) {
            await stalled
            // 放弃之后才写进来的内容不能影响任何东西。
            onProgress?.({ progress: 99 })
            fs.writeFileSync(savePath, '<html>late garbage</html>', 'utf8')
            return { success: true }
          }
          fs.writeFileSync(savePath, kind === 'sums' ? sumsFor(NEW_BINARY) : NEW_BINARY, 'utf8')
          return { success: true }
        }
      )
      return {
        download,
        urls,
        get exeUrls() {
          return urls.filter(url => !isSumsUrl(url))
        },
        release: () => releaseStalled?.(),
      }
    }

    it('单个源超过时长上限就换下一个源', async () => {
      writePin(PINNED_VERSION)
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
      expect(stub.exeUrls).toHaveLength(2)
      expect(fs.readFileSync(runtimePath, 'utf8')).toBe(NEW_BINARY)

      // 被放弃的那次下载最终写完时：不动 exe，不再上报进度，临时文件被清掉。
      stub.release()
      await vi.waitFor(() =>
        expect(fs.readdirSync(path.dirname(runtimePath))).toEqual(['auto-mas-runtime.exe'])
      )
      expect(fs.readFileSync(runtimePath, 'utf8')).toBe(NEW_BINARY)
      expect(progress.some(update => update.progress === 99)).toBe(false)
    })

    it('校验清单本身停滞时也受单源上限约束，换下一个源', async () => {
      writePin(PINNED_VERSION)
      const stub = createStallingDownload(1, 'sums')
      const startedAt = Date.now()

      const outcome = await syncRuntimeBinary(
        syncOptions({ download: stub.download, sourceTimeoutMs: 20 })
      )

      // 清单的独立上限是 30 秒，但不能超过单源上限：这里必须在 20ms 量级就换源。
      expect(Date.now() - startedAt).toBeLessThan(2000)
      expect(outcome.status).toBe('upgraded')
      // 第一个源只请求了清单就被放弃。
      expect(stub.exeUrls).toEqual([buildRuntimeBinarySources(PINNED_VERSION)[1].url])
      expect(fs.readFileSync(runtimePath, 'utf8')).toBe(NEW_BINARY)

      stub.release()
      await vi.waitFor(() =>
        expect(fs.readdirSync(path.dirname(runtimePath))).toEqual(['auto-mas-runtime.exe'])
      )
      expect(fs.readFileSync(runtimePath, 'utf8')).toBe(NEW_BINARY)
    })

    it('单源上限不超过本轮剩余预算', async () => {
      writePin(PINNED_VERSION)
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
      expect(stub.exeUrls.length).toBeGreaterThanOrEqual(1)
      expect(fs.readFileSync(runtimePath, 'utf8')).toBe(OLD_BINARY)
      stub.release()
    })
  })

  describe('目标被占用时的替换', () => {
    const busyError = () =>
      Object.assign(new Error('EBUSY: resource busy or locked'), { code: 'EBUSY' })

    const isOverwrite = (from: string, to: string) =>
      to === runtimePath && from.includes('.download')

    afterEach(() => {
      renameHook.before = null
      renameHook.calls.length = 0
    })

    it('直接覆盖失败时先把旧文件改名让路，成功后清掉旧文件', async () => {
      writePin(PINNED_VERSION)
      const { download } = createDownload(() => ({ success: true, content: NEW_BINARY }))
      let overwriteAttempts = 0
      // 正在运行的 exe 不能被覆盖，但可以被改名：只拦「新文件盖到 exe 路径」的第一次。
      renameHook.before = (from, to) => {
        if (!isOverwrite(from, to)) return
        overwriteAttempts += 1
        if (overwriteAttempts === 1) throw busyError()
      }

      const outcome = await syncRuntimeBinary(syncOptions({ download }))

      expect(outcome.status).toBe('upgraded')
      expect(fs.readFileSync(runtimePath, 'utf8')).toBe(NEW_BINARY)
      expect(fs.readdirSync(path.dirname(runtimePath))).toEqual(['auto-mas-runtime.exe'])
      // 让路：旧 exe 先改名成 .old，再把新文件挪过来。
      expect(renameHook.calls).toContainEqual([runtimePath, `${runtimePath}.old`])
      expect(overwriteAttempts).toBe(2)
    })

    it('让路后仍挪不进去时把旧文件改回来，exe 保持原样', async () => {
      writePin(PINNED_VERSION)
      const { download } = createDownload(() => ({ success: true, content: NEW_BINARY }))
      renameHook.before = (from, to) => {
        if (isOverwrite(from, to)) throw busyError()
      }

      const outcome = await syncRuntimeBinary(syncOptions({ download }))

      expect(outcome.status).toBe('failed')
      expect(outcome.code).toBe(RUNTIME_BINARY_REPLACE_FAILED)
      expect(outcome.error).toContain('EBUSY')
      expect(fs.readFileSync(runtimePath, 'utf8')).toBe(OLD_BINARY)
      expect(fs.readdirSync(path.dirname(runtimePath))).toEqual(['auto-mas-runtime.exe'])
      // 回滚：让路的 .old 被改回 exe 路径。
      expect(renameHook.calls).toContainEqual([`${runtimePath}.old`, runtimePath])
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
