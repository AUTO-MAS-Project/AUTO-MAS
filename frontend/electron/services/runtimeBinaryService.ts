/**
 * Runtime 可执行文件随本体一起更新
 *
 * `auto-mas-runtime.exe` 由安装包捆绑进 `resources/`，此前只能靠重装整包升级：本体源码
 * （`repo/`）能被 `bootstrap --version` 换成新版本，Runtime 却停在装机那天的版本，于是
 * 「新本体 + 旧 Runtime」这种从未联调过的组合会在用户机器上出现。
 *
 * 这里把 Runtime 的版本钉扎在本体源码里（`res/runtime-version.txt`），让它跟着源码走：
 *
 * 1. 发布 CI 从仓库根的 `res/runtime-version.txt` 读版本，下载该 Release 的 exe、按同一
 *    Release 的 `SHA256SUMS.txt` 校验后捆绑进安装包；
 * 2. **第 0 步**：首次初始化与本体更新在跑 `bootstrap` 之前，先到目标发布分支
 *    （`release/<版本>`）上读远端的 `res/runtime-version.txt`，与磁盘上那个 exe 自报的版本
 *    对一遍，不一致就先把 exe 换成钉扎的那一版，再交给它去 bootstrap
 *    （{@link alignRuntimeBinaryWithVersion}）。这样克隆源码的已经是配套的 Runtime，
 *    而不是装机那天的旧版本；
 * 3. 每次经 Runtime 启动后端时（`bootstrap --if-needed` 之后、`supervise` 之前）再按
 *    `<app-root>/repo/res/runtime-version.txt` 兜底核对一次，不联网、失败不阻断
 *    （{@link syncRuntimeBinary}）。
 *
 * 几条刻意的取舍：
 *
 * - **判据是版本号相等，不是「钉扎的更新才换」。** 本体回退到旧版本时 Runtime 必须跟着退
 *   回去，否则回退这条路仍然会得到没联调过的组合。
 * - **判身份用自报版本，不用文件哈希；哈希只用来校验下载物。** 理由见
 *   {@link readInstalledRuntimeVersion}。
 * - **仓库里只钉版本号，哈希取自 Release 自带的 `SHA256SUMS.txt`，而且清单只从项目自己
 *   控制的 GitHub / CNB 取。** 与发布 CI、本地打包脚本同一份清单、同一种校验；仓库不再抄一份
 *   哈希，也就没有「版本改了哈希没改」的失败面。gh-proxy 一类第三方代理只负责下 exe：让同一个
 *   代理同时给出文件和信任依据，它被入侵时就能配一组互相匹配的恶意文件与哈希，校验形同虚设。
 * - **原地替换，不做多版本并存。** 校验通过的新文件直接换到原路径，`resolveRuntimeExecutable()`
 *   与所有持有旧路径字符串的地方都不用动——`RuntimeClient` 每条命令都是重新 spawn 同一个
 *   路径。旧文件先改名为 `<exe>.old` 让路，新文件确认跑得起来才清掉备份，见
 *   {@link replaceRuntimeBinary}。
 * - **下载首选 CNB，再走 gh-proxy 家族，GitHub 官方兜底。** 顺序自己实现，不复用
 *   `MirrorRotationService`：后者的 `sortMirrors()` 会把 key 里含 `github` 的源提到最前
 *   （为初始化拉源码的测试版场景加的），套到这里正好把国内用户最连不上的官方源排到第一个。
 * - **第 0 步失败就停下，启动时的兜底核对失败不阻断。** 第 0 步所在的两条流程紧接着就要
 *   联网克隆源码，连十几个字节的钉扎都拿不到时克隆也必挂，与其让 bootstrap 报一个看不懂的
 *   错，不如在这里用一句能照着做的话停下来等用户重试；启动时旧 Runtime 仍然能监督后端，
 *   把用户卡在「更新完就打不开」比多跑一版旧 Runtime 糟得多。
 */

import * as crypto from 'crypto'
import * as fs from 'fs'
import * as path from 'path'

import { SmartDownloader } from './downloadService'
import { getLogger } from './logger'
import {
  RUNTIME_BACKUP_SUFFIX,
  RUNTIME_EXE_ENV,
  createRuntimeClient,
  recoverRuntimeBackup,
} from './runtime'

const logger = getLogger('Runtime二进制')

// ==================== 钉扎 ====================

/**
 * 钉扎文件在源码树里的相对路径，仓库根与受管 `repo/` 下同名同位。
 *
 * 与发布 CI（`.github/workflows/build-app.yml`）、本地打包脚本
 * （`scripts/build-local-package.ps1`）读的是同一个文件：一行版本号，例如 `v0.1.7`。
 */
export const RUNTIME_PIN_RELATIVE_PATH = path.join('res', 'runtime-version.txt')

/** 钉扎文件在仓库里的 URL 路径段，远端读取时拼在分支名后面。 */
const RUNTIME_PIN_URL_PATH = 'res/runtime-version.txt'

/** 钉扎文件的大小上限：它只有一行版本号，超过说明读到的不是它。 */
const MAX_PIN_FILE_BYTES = 64 * 1024

/**
 * 版本号的合法形态：`v` 加点分数字，可跟一段预发布/构建后缀。
 *
 * 与发布 CI、本地打包脚本和 `runtimeUpdateService` 里那条同源——版本号会被拼进下载 URL，
 * 带 `/` 或空白的值必须在这里挡掉，不能指望远端返回 404。
 */
const RUNTIME_VERSION_PATTERN = /^v\d+(\.\d+)*([-+][0-9A-Za-z.-]+)?$/

const SHA256_PATTERN = /^[0-9a-f]{64}$/

/** 本体对 Runtime 版本的钉扎。 */
export interface RuntimeBinaryPin {
  /** 发布标签，同时是 Release 的 tag 与资产名里的版本段，例如 `v0.1.7`。 */
  version: string
}

/** 把钉扎文件的正文解析成版本号；空白、非法形态返回 null。 */
export function parseRuntimeBinaryPin(text: string): RuntimeBinaryPin | null {
  const version = text.trim()
  return RUNTIME_VERSION_PATTERN.test(version) ? { version } : null
}

/**
 * 读取并校验受管源码里的钉扎文件（启动时兜底核对用）。
 *
 * 文件缺失、为空、版本号非法一律返回 null（调用方按「本体没有钉扎」处理而不是报错）：
 * 携带该文件之前发布的本体版本本来就没有它，回退到那些版本时不该把启动流程弄失败。
 */
export function readRuntimeBinaryPin(sourceRoot: string): RuntimeBinaryPin | null {
  const pinPath = path.join(sourceRoot, RUNTIME_PIN_RELATIVE_PATH)
  try {
    const stat = fs.statSync(pinPath)
    if (!stat.isFile() || stat.size > MAX_PIN_FILE_BYTES) return null

    const text = fs.readFileSync(pinPath, 'utf8')
    const pin = parseRuntimeBinaryPin(text)
    if (!pin) {
      logger.warn(`${pinPath} 的版本号非法，忽略该钉扎: ${JSON.stringify(text.trim())}`)
    }
    return pin
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code !== 'ENOENT') {
      logger.warn(
        `读取 ${pinPath} 失败，按未钉扎处理: ${
          error instanceof Error ? error.message : String(error)
        }`
      )
    }
    return null
  }
}

// ==================== 远端钉扎（第 0 步） ====================

/** 本体仓库：远端钉扎从它的发布分支上读。与 `mirrorService` 的 `repo` 源指向同一个仓库。 */
const APP_REPO = 'AUTO-MAS-Project/AUTO-MAS'

/**
 * 目标版本对应的发布分支。
 *
 * 与 Runtime `internal/gitrepo/target.go` 的 `releasePrefix + version` 同一条规则：
 * bootstrap 克隆的就是这条分支，第 0 步读的钉扎必须来自同一条分支，两边才是同一份文件。
 */
export function runtimeReleaseBranch(version: string): string {
  return `release/${version}`
}

/** 一个只读文本的远端来源（钉扎文件、校验清单）。 */
export interface RuntimeTextSource {
  key: string
  name: string
  url: string
}

/**
 * 远端钉扎的两个来源：CNB 与 GitHub，同时发起、先拿到的先用。
 *
 * 只要这两个：CNB 是上游每次 push 都镜像过去的官方镜像（`sync-cnb.yml`），GitHub 是原件；
 * 两者都是仓库自己的地址，没有第三方代理的缓存与改写。文件只有一行，不值得再引入
 * gh-proxy 家族——它们对 raw 内容的缓存会让钉扎落后于分支。
 */
export function buildRuntimePinSources(version: string): RuntimeTextSource[] {
  const branch = runtimeReleaseBranch(version)
  return [
    {
      key: 'cnb',
      name: 'CNB',
      url: `https://cnb.cool/${APP_REPO}/-/git/raw/${branch}/${RUNTIME_PIN_URL_PATH}`,
    },
    {
      key: 'github',
      name: 'GitHub',
      url: `https://raw.githubusercontent.com/${APP_REPO}/${branch}/${RUNTIME_PIN_URL_PATH}`,
    },
  ]
}

/** 单个文本来源的时长上限：文件不到一百字节，超过这个时间就是这条路不通。 */
export const RUNTIME_TEXT_FETCH_TIMEOUT_MS = 15 * 1000

/** 远端读取的三种结局。 */
export type RemoteRuntimePinLookup =
  | { status: 'pinned'; pin: RuntimeBinaryPin; source: string }
  /** 两个来源都明确回答 404：该版本发布时还没有这个机制，按未钉扎处理。 */
  | { status: 'unpinned' }
  /** 没有一个来源给出结论：网络不通、代理改写了正文、一个 404 另一个失败等。 */
  | { status: 'unavailable'; error: string }

/** 单个来源的抓取结果，供 {@link fetchFirstValidText} 归并。 */
export type RuntimePinFetchOutcome =
  | { kind: 'text'; text: string }
  | { kind: 'missing' }
  | { kind: 'failed'; error: string }

export type RuntimePinFetcher = (url: string, timeoutMs: number) => Promise<RuntimePinFetchOutcome>

/** 默认抓取：跟随重定向，只认 2xx；404 单独区分出来，其余状态码与网络错误都算失败。 */
const defaultFetchText: RuntimePinFetcher = async (url, timeoutMs) => {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), timeoutMs)
  try {
    const response = await fetch(url, {
      signal: controller.signal,
      headers: { 'Cache-Control': 'no-cache' },
    })
    if (response.status === 404) return { kind: 'missing' }
    if (!response.ok) return { kind: 'failed', error: `HTTP ${response.status}` }
    const text = await response.text()
    if (text.length > MAX_PIN_FILE_BYTES) return { kind: 'failed', error: '返回的内容过大' }
    return { kind: 'text', text }
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error)
    return {
      kind: 'failed',
      error: controller.signal.aborted ? `${Math.ceil(timeoutMs / 1000)} 秒内没有响应` : message,
    }
  } finally {
    clearTimeout(timer)
  }
}

export interface FetchRemoteRuntimeBinaryPinOptions {
  timeoutMs?: number
  /** 测试注入；默认用全局 `fetch`。 */
  fetchText?: RuntimePinFetcher
}

type FirstValidTextOutcome<T> =
  | { kind: 'found'; value: T; source: string }
  /** 全部来源都明确回答 404。 */
  | { kind: 'missing' }
  | { kind: 'unavailable'; error: string }

/**
 * 从几个可信来源并行读同一份小文本，先给出合法内容的那个胜出。
 *
 * 归并规则：任一来源给出合法内容 → `found`（立刻返回，不等其余）；否则**全部**来源都明确
 * 回答 404 → `missing`；其余一律 `unavailable`。「一个 404、另一个网络失败」也是
 * `unavailable`：404 的那个可能只是镜像还没同步（CNB 落后 GitHub 几秒的窗口），失败的那个
 * 才可能有答案，此时判成「没有」等于用不确定的信息放行。
 */
function fetchFirstValidText<T>(
  what: string,
  sources: RuntimeTextSource[],
  parse: (text: string) => T | null,
  invalidReason: string,
  options: FetchRemoteRuntimeBinaryPinOptions
): Promise<FirstValidTextOutcome<T>> {
  const fetchText = options.fetchText ?? defaultFetchText
  const timeoutMs = options.timeoutMs ?? RUNTIME_TEXT_FETCH_TIMEOUT_MS

  return new Promise(resolve => {
    let pending = sources.length
    let settled = false
    let missingCount = 0
    const failures: string[] = []

    const conclude = (): void => {
      if (settled) return
      settled = true
      if (missingCount === sources.length) {
        resolve({ kind: 'missing' })
        return
      }
      resolve({ kind: 'unavailable', error: failures.join('；') })
    }

    for (const source of sources) {
      logger.debug(`从 ${source.name} 读取${what}: ${source.url}`)
      fetchText(source.url, timeoutMs)
        .then(
          outcome => outcome,
          (error): RuntimePinFetchOutcome => ({
            kind: 'failed',
            error: error instanceof Error ? error.message : String(error),
          })
        )
        .then(outcome => {
          if (settled) return
          if (outcome.kind === 'text') {
            const value = parse(outcome.text)
            if (value !== null) {
              settled = true
              logger.info(`${what}来自 ${source.name}`)
              resolve({ kind: 'found', value, source: source.key })
              return
            }
            // 代理或门户页把错误页当正文返回时会走到这里；不能把它当 404。
            failures.push(`${source.name}: ${invalidReason}`)
          } else if (outcome.kind === 'missing') {
            missingCount += 1
            failures.push(`${source.name}: HTTP 404`)
          } else {
            failures.push(`${source.name}: ${outcome.error}`)
          }
          pending -= 1
          if (pending === 0) conclude()
        })
    }
  })
}

/**
 * 到目标发布分支上读 Runtime 钉扎：两个来源并行，先拿到合法版本号的那个胜出。
 *
 * 只有两个来源都明确回答 404 才算「目标分支没有钉扎」；归并规则见 {@link fetchFirstValidText}。
 */
export async function fetchRemoteRuntimeBinaryPin(
  version: string,
  options: FetchRemoteRuntimeBinaryPinOptions = {}
): Promise<RemoteRuntimePinLookup> {
  const outcome = await fetchFirstValidText(
    'Runtime 钉扎',
    buildRuntimePinSources(version),
    parseRuntimeBinaryPin,
    '返回的内容不是版本号',
    options
  )
  switch (outcome.kind) {
    case 'found':
      logger.info(`${runtimeReleaseBranch(version)} 钉扎 Runtime ${outcome.value.version}`)
      return { status: 'pinned', pin: outcome.value, source: outcome.source }
    case 'missing':
      logger.info(`${runtimeReleaseBranch(version)} 上没有 ${RUNTIME_PIN_URL_PATH}，按未钉扎处理`)
      return { status: 'unpinned' }
    case 'unavailable':
      return { status: 'unavailable', error: outcome.error }
  }
}

// ==================== 下载源 ====================

/** Runtime 发布仓库，与发布 CI 的 `gh release download -R` 同一个；CNB 上同名镜像。 */
const RUNTIME_RELEASE_REPO = 'AUTO-MAS-Project/AUTO-MAS-Runtime'

/** Release 资产的下载前缀：`<prefix>/<version>/<asset>`。 */
interface RuntimeReleaseSource {
  key: string
  name: string
  release: (version: string) => string
  /** 项目自己控制的来源：只有它们给出的校验清单算数。 */
  trusted: boolean
}

const RUNTIME_RELEASE_SOURCES: readonly RuntimeReleaseSource[] = [
  {
    key: 'cnb',
    name: 'CNB',
    release: version => `https://cnb.cool/${RUNTIME_RELEASE_REPO}/-/releases/download/${version}`,
    trusted: true,
  },
  {
    key: 'ghproxy_cloudflare',
    name: 'gh-proxy (Cloudflare)',
    release: version =>
      `https://gh-proxy.com/https://github.com/${RUNTIME_RELEASE_REPO}/releases/download/${version}`,
    trusted: false,
  },
  {
    key: 'ghproxy_fastly',
    name: 'gh-proxy (Fastly CDN)',
    release: version =>
      `https://cdn.gh-proxy.com/https://github.com/${RUNTIME_RELEASE_REPO}/releases/download/${version}`,
    trusted: false,
  },
  {
    key: 'ghproxy_edgeone',
    name: 'gh-proxy (EdgeOne)',
    release: version =>
      `https://edgeone.gh-proxy.com/https://github.com/${RUNTIME_RELEASE_REPO}/releases/download/${version}`,
    trusted: false,
  },
  {
    key: 'github',
    name: 'GitHub 官方',
    release: version => `https://github.com/${RUNTIME_RELEASE_REPO}/releases/download/${version}`,
    trusted: true,
  },
]

/** 每个 Release 自带的校验清单，与发布 CI、本地打包脚本用的是同一份。 */
const RUNTIME_SUMS_ASSET = 'SHA256SUMS.txt'

/** 一个候选的 exe 下载源。 */
export interface RuntimeBinarySource {
  key: string
  name: string
  /** `auto-mas-runtime-<version>.exe` */
  url: string
}

/** Release 里 exe 资产的文件名，也是 `SHA256SUMS.txt` 里对应行的第二列。 */
export function runtimeAssetName(version: string): string {
  return `auto-mas-runtime-${version}.exe`
}

/**
 * exe 的候选下载地址，按尝试顺序排列。
 *
 * CNB 在最前：它是维护者要求的首选（国内直连、Release 资产已同步过去），实测下载走
 * `asset.cnb.cool` 的 302；随后是这批用户实测能连上的 gh-proxy 家族，官方源永远兜底在最后。
 * 这份表刻意写死在代码里而不进 `mirror_config.json`：云端配置是整体替换 `mirrors` 对象的，
 * 新增一类会在云端还没跟上时变成 undefined。
 */
export function buildRuntimeBinarySources(version: string): RuntimeBinarySource[] {
  const asset = runtimeAssetName(version)
  return RUNTIME_RELEASE_SOURCES.map(source => ({
    key: source.key,
    name: source.name,
    url: `${source.release(version)}/${asset}`,
  }))
}

/**
 * 校验清单的来源：只有项目自己控制的 CNB 与 GitHub。
 *
 * 信任依据必须与被校验的文件来自不同的信任域：代理只能拿到 exe，拿不到「这份 exe 该长什么样」
 * 的话语权。清单几十字节，两个来源并行、先到先用，与钉扎同一套读取逻辑。
 */
export function buildRuntimeSumsSources(version: string): RuntimeTextSource[] {
  return RUNTIME_RELEASE_SOURCES.filter(source => source.trusted).map(source => ({
    key: source.key,
    name: source.name,
    url: `${source.release(version)}/${RUNTIME_SUMS_ASSET}`,
  }))
}

// ==================== 校验 ====================

/**
 * 从 `SHA256SUMS.txt` 里找出某个资产的 SHA-256（小写十六进制）。
 *
 * 清单是 `sha256sum` 风格：每行「哈希、空白、文件名」，行尾可能是 CRLF。只认第二列与资产名
 * 完全相等、第一列是 64 位十六进制的那一行；没有这一行或格式不对都返回 null，让调用方换源。
 */
export function parseRuntimeSums(text: string, asset: string): string | null {
  for (const rawLine of text.split(/\r?\n/)) {
    const columns = rawLine.trim().split(/\s+/)
    if (columns.length < 2 || columns[1] !== asset) continue
    const hash = columns[0].toLowerCase()
    if (SHA256_PATTERN.test(hash)) return hash
  }
  return null
}

/** 可信来源给出的期望哈希。 */
export type TrustedRuntimeHashLookup =
  | { status: 'found'; hash: string; source: string }
  | { status: 'unavailable'; error: string }

/**
 * 从可信来源取钉扎版本 exe 的期望 SHA-256。
 *
 * 两个来源都 404 意味着该 Release 没有清单（或没有这个资产），同样按取不到处理：没有可信
 * 的哈希就不能装任何东西。
 */
export async function fetchTrustedRuntimeHash(
  version: string,
  options: FetchRemoteRuntimeBinaryPinOptions = {}
): Promise<TrustedRuntimeHashLookup> {
  const asset = runtimeAssetName(version)
  const outcome = await fetchFirstValidText(
    `Runtime ${version} 的校验清单`,
    buildRuntimeSumsSources(version),
    text => parseRuntimeSums(text, asset),
    `清单里没有 ${asset} 的有效 SHA-256`,
    options
  )
  switch (outcome.kind) {
    case 'found':
      return { status: 'found', hash: outcome.value, source: outcome.source }
    case 'missing':
      return { status: 'unavailable', error: `Release ${version} 没有校验清单` }
    case 'unavailable':
      return { status: 'unavailable', error: outcome.error }
  }
}

/** 流式计算 SHA-256；文件不存在或读失败返回 null。 */
export function hashFileSha256(filePath: string): Promise<string | null> {
  return new Promise(resolve => {
    const hash = crypto.createHash('sha256')
    const stream = fs.createReadStream(filePath)
    stream.on('error', () => resolve(null))
    stream.on('data', chunk => hash.update(chunk))
    stream.on('end', () => resolve(hash.digest('hex')))
  })
}

/**
 * 问磁盘上那个 exe 自己是什么版本（`auto-mas-runtime.exe version`）。
 *
 * **判据是它自报的版本而不是文件哈希**：发布资产的哈希只能证明「从网上下到的那份没坏」，
 * 一旦本地那份被任何后处理动过一个字节（重签名、杀软隔离后还原、打包工具改写），哈希就
 * 永远对不上，而版本没变——按哈希判会让每次启动都白下载十几兆。版本比对不受这些影响。
 *
 * 跑不起来或没报版本时返回 null，调用方按「需要换」处理：一个连版本都问不出来的 exe，
 * 本来也该换掉。
 */
async function readInstalledRuntimeVersion(
  runtimePath: string,
  appRoot: string
): Promise<string | null> {
  try {
    const client = createRuntimeClient({ runtimePath, appRoot })
    const outcome = await client.run(['version'])
    if (!outcome.success) return null

    const reported = outcome.result.details.runtimeVersion ?? outcome.hello?.runtimeVersion
    return typeof reported === 'string' && reported.trim() !== '' ? reported.trim() : null
  } catch (error) {
    logger.warn(
      `查询现有 Runtime 版本失败: ${error instanceof Error ? error.message : String(error)}`
    )
    return null
  }
}

// ==================== 同步结果 ====================

export type RuntimeBinarySyncStatus = 'current' | 'upgraded' | 'skipped' | 'failed' | 'cancelled'

export const RUNTIME_BINARY_DOWNLOAD_FAILED = 'RUNTIME_BINARY_DOWNLOAD_FAILED'
export const RUNTIME_BINARY_REPLACE_FAILED = 'RUNTIME_BINARY_REPLACE_FAILED'
/** 与 Runtime 自己的取消码同名：调用方对两者的处置完全一样（源码一动没动）。 */
export const RUNTIME_BINARY_CANCELLED = 'OPERATION_CANCELLED'

export interface RuntimeBinarySyncResult {
  /**
   * - `current`：磁盘上的 exe 自报的版本就是钉扎的那一版；
   * - `upgraded`：已经换成钉扎的那一版；
   * - `skipped`：`AUTO_MAS_RUNTIME_EXE` 指定了自带的 Runtime，不去动开发者的文件；
   * - `failed`：需要换但没换成，`error` 是给用户看的一句话，`code` 供界面分流；
   * - `cancelled`：调用方在中途要求取消，exe 保持原样。
   */
  status: RuntimeBinarySyncStatus
  pin: RuntimeBinaryPin
  error?: string
  code?: string
}

export interface RuntimeBinarySyncProgress {
  /** 0~100；总量未知时停在 0。 */
  progress: number
  message: string
  /** 正在下载的资产名，供界面的网络细节行使用。 */
  item?: string
  /** 当前字节来自哪个源的 key。 */
  source?: string
  bytesPerSecond?: number
  /** 已下载字节数。 */
  current?: number
  /** 总字节数。 */
  total?: number
}

/** 下载器回调的形状；`SmartDownloader` 多给的字段原样透传到进度里。 */
export interface RuntimeBinaryDownloadProgress {
  progress: number
  speed?: number
  downloadedSize?: number
  totalSize?: number
}

export type RuntimeBinaryDownloader = (
  url: string,
  savePath: string,
  onProgress?: (progress: RuntimeBinaryDownloadProgress) => void
) => Promise<{ success: boolean; error?: string }>

export interface RuntimeBinarySyncOptions {
  /** 当前生效的 `auto-mas-runtime.exe` 路径。 */
  runtimePath: string
  /** 传给 Runtime 的 `--app-root`，这里只用于问它自己的版本。 */
  appRoot: string
  /** 要对齐到的版本。 */
  pin: RuntimeBinaryPin
  onProgress?: (progress: RuntimeBinarySyncProgress) => void
  /**
   * 调用方的取消判据：每换一个源、每下完一个文件都问一次，为真就不再往下走。
   *
   * 下载器没有取消接口，在途的那次下载会继续跑到结束，只是不再等它、也不用它的结果。
   */
  isCancelled?: () => boolean
  /** 本轮同步的总时间预算，缺省 {@link RUNTIME_BINARY_SYNC_BUDGET_MS}。 */
  budgetMs?: number
  /** 单个下载源的时长上限，缺省 {@link RUNTIME_BINARY_SOURCE_TIMEOUT_MS}。 */
  sourceTimeoutMs?: number
  /** 测试注入；默认用真实下载器。 */
  download?: RuntimeBinaryDownloader
  /** 测试注入；校验清单的抓取，默认用全局 `fetch`。 */
  fetchText?: RuntimePinFetcher
  /** 测试注入；默认真的去跑 `auto-mas-runtime.exe version`。 */
  readVersion?: (runtimePath: string, appRoot: string) => Promise<string | null>
}

// ==================== 同步 ====================

/**
 * 下载中的临时文件与让路后的旧文件都用固定后缀，便于下次同步清扫残留。
 *
 * 临时文件名是 `<exe>.download-<token>`，每次向一个源发起下载都换一个：下载器不支持取消，
 * 放弃一个慢源之后它仍在后台往自己的文件里写，若各源共用一个文件名，它会在下一个源
 * 校验通过之后把文件截断重写，让一个没校验过的文件盖到 exe 上。
 */
const DOWNLOAD_SUFFIX = '.download'
const BACKUP_SUFFIX = RUNTIME_BACKUP_SUFFIX

/**
 * 一轮同步的总时间预算。
 *
 * 卡死的连接由 `SmartDownloader` 自己的超时兜住（HEAD 10 秒、分片 30 秒空闲），但「连得上、
 * 就是慢」不会触发那些超时——五个源依次各拉一遍十几兆，最坏能把启动挂上一个钟头。这里在
 * 换下一个源之前查一次预算，超了就当本轮失败，继续用现有 Runtime 启动，下次启动再试；
 * 已经开始的那一次由 {@link RUNTIME_BINARY_SOURCE_TIMEOUT_MS} 兜住。
 */
export const RUNTIME_BINARY_SYNC_BUDGET_MS = 10 * 60 * 1000

/**
 * 单个下载源的时长上限，与剩余预算取小。
 *
 * 取总预算的一半：一个被限速到十几 KB/s 的源最多只能吃掉半份预算，保证至少还有机会换
 * 一个源。超时后只是不再等它——下载器没有取消接口，那次下载会继续跑到自己结束为止，
 * 所以每次尝试都写自己的临时文件（见 {@link DOWNLOAD_SUFFIX}），结束后再顺手清掉。
 */
export const RUNTIME_BINARY_SOURCE_TIMEOUT_MS = RUNTIME_BINARY_SYNC_BUDGET_MS / 2

const defaultDownload: RuntimeBinaryDownloader = (url, savePath, onProgress) =>
  new SmartDownloader().download(url, savePath, onProgress)

/** 正在进行的那一次同步；后来者复用它的结果而不是再开一份下载。 */
interface SyncFlight {
  promise: Promise<RuntimeBinarySyncResult>
  pin: RuntimeBinaryPin
  /** 所有等着这次同步的调用方的进度回调，后来者也能看到进度。 */
  listeners: Set<(progress: RuntimeBinarySyncProgress) => void>
}

let inFlight: SyncFlight | null = null

/**
 * 让磁盘上的 Runtime 与给定钉扎一致。
 *
 * 只在没有任何进程持有 exe 时调用：第 0 步在 bootstrap 之前（此时后端已停或尚未启动），
 * 启动兜底在 `bootstrap --if-needed` 之后、`supervise` 之前。
 *
 * 同一时刻只允许一次同步在途：两个挂接点之间隔着有意重启标志，正常界面操作不会撞上，
 * 但开发者工具里的重启按钮与 `backend-start` IPC 能在更新链路的同步还没结束时再触发一次
 * 启动。两份下载各写各的临时文件不会互相污染，但会白拉一份十几兆并把同一个 exe 换两次，
 * 所以后来者直接等前一次的结果。
 */
export function syncRuntimeBinary(
  options: RuntimeBinarySyncOptions
): Promise<RuntimeBinarySyncResult> {
  if (inFlight) {
    if (inFlight.pin.version !== options.pin.version) {
      // 要的不是同一版（启动兜底按本地钉扎、第 0 步按远端钉扎，两者可能不同步）：拿前一次的
      // 结果当自己的会让第 0 步误判「已一致」放行 bootstrap，所以等它落地后再按本次要求同步。
      logger.info(
        `已有一次到 ${inFlight.pin.version} 的 Runtime 同步在进行，等它结束后再同步到 ${options.pin.version}`
      )
      const previous = inFlight.promise
      const rerun = (): Promise<RuntimeBinarySyncResult> => syncRuntimeBinary(options)
      return previous.then(rerun, rerun)
    }
    logger.info('已有一次 Runtime 同步在进行，等待其结果')
    if (options.onProgress) inFlight.listeners.add(options.onProgress)
    return inFlight.promise
  }

  const listeners: SyncFlight['listeners'] = new Set()
  if (options.onProgress) listeners.add(options.onProgress)
  const promise = runSync({
    ...options,
    onProgress: progress => {
      for (const listener of listeners) listener(progress)
    },
  }).finally(() => {
    if (inFlight?.promise === promise) inFlight = null
  })
  inFlight = { promise, pin: options.pin, listeners }
  return promise
}

/** 开发者用 `AUTO_MAS_RUNTIME_EXE` 指到自己编译的那份时，绝不能被线上钉扎覆盖掉。 */
export function isDeveloperRuntime(runtimePath: string): boolean {
  const configured = process.env[RUNTIME_EXE_ENV]?.trim()
  return Boolean(configured) && path.resolve(configured as string) === path.resolve(runtimePath)
}

async function runSync(options: RuntimeBinarySyncOptions): Promise<RuntimeBinarySyncResult> {
  const { runtimePath, appRoot, pin } = options

  if (isDeveloperRuntime(runtimePath)) {
    logger.info(`${RUNTIME_EXE_ENV} 指定了 Runtime，跳过随本体更新`)
    return { status: 'skipped', pin }
  }

  const readVersion = options.readVersion ?? readInstalledRuntimeVersion
  const backupPath = `${runtimePath}${BACKUP_SUFFIX}`

  // 上次替换半途而废（新文件没挪进来、旧文件也改不回去）会只剩 `.old`：先把它找回来。
  // 定位 exe 时已经做过一次（resolveRuntimeExecutable），这里再做是为了显式传入的路径。
  recoverRuntimeBackup(runtimePath)
  // 上次被打断（应用退出、断电）留下的半截下载在这里统一清掉，不等到真要替换时才清：
  // 版本一直对得上时那条路根本不会走到，十几兆就会一直留在安装目录里。
  removeStaleDownloads(runtimePath)

  let installed = await readVersion(runtimePath, appRoot)
  if (installed === null && fs.existsSync(backupPath)) {
    // exe 跑不起来而备份还在（上次换上的新文件跑不起来、换回去又没成功）：备份是最后一份
    // 能跑的，先把它换回来再谈更新。换不回来（坏文件被占用）就让它留着，下面替换时也不会
    // 拿坏文件去覆盖它。
    if (restoreBackup(runtimePath, backupPath)) installed = await readVersion(runtimePath, appRoot)
  }
  // 备份只在正式 exe 存在且跑得起来之后才清：它是替换失败时唯一能救回来的东西。
  if (installed !== null) removeQuietly(backupPath)

  if (installed === pin.version) {
    logger.debug(`Runtime 已是本体要求的 ${pin.version}`)
    return { status: 'current', pin }
  }
  if (options.isCancelled?.()) return { status: 'cancelled', pin, code: RUNTIME_BINARY_CANCELLED }

  logger.info(`现有 Runtime ${installed ?? '版本未知'}，本体要求 ${pin.version}，开始下载并替换`)

  const downloaded = await downloadPinned(pin, runtimePath, options)
  if (downloaded.status === 'cancelled') {
    return { status: 'cancelled', pin, code: RUNTIME_BINARY_CANCELLED }
  }
  if (downloaded.status === 'failed') {
    return {
      status: 'failed',
      pin,
      error: describeDownloadFailure(pin, runtimePath, downloaded.error),
      code: RUNTIME_BINARY_DOWNLOAD_FAILED,
    }
  }

  let backedUp: boolean
  try {
    backedUp = replaceRuntimeBinary(runtimePath, downloaded.downloadPath, backupPath)
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error)
    logger.error(`替换 Runtime 可执行文件失败: ${message}`)
    removeQuietly(downloaded.downloadPath)
    return {
      status: 'failed',
      pin,
      error: describeReplaceFailure(runtimePath, error),
      code: RUNTIME_BINARY_REPLACE_FAILED,
    }
  }

  // 新文件跑得起来才算换成：哈希只证明它是 Release 里那份，证明不了这台机器上能执行
  // （安全软件拦截、缺运行库）。跑不起来就把旧文件换回去，别让用户手里连一个能用的都没有。
  const verified = await readVersion(runtimePath, appRoot)
  if (verified === null) {
    logger.error(`下载到的 Runtime ${pin.version} 无法运行${backedUp ? '，恢复原文件' : ''}`)
    const backup: BackupOutcome = !backedUp
      ? 'none'
      : restoreBackup(runtimePath, backupPath)
        ? 'restored'
        : 'kept'
    return {
      status: 'failed',
      pin,
      error: describeUnrunnableReplacement(pin, runtimePath, backup),
      code: RUNTIME_BINARY_REPLACE_FAILED,
    }
  }
  if (backedUp) removeQuietly(backupPath)
  if (verified !== pin.version) {
    // Release 里的文件自报的版本与 tag 不一致，是发布侧的问题；文件本身按可信清单验过，
    // 照常放行。后果是「版本相等」永远不成立：每次启动兜底与每次第 0 步都会再下载、再换
    // 一遍，直到发布侧修正——有意为之，宁可多下也不装来路不明的东西。
    logger.warn(
      `Runtime ${pin.version} 的可执行文件自报版本为 ${verified}，与 tag 不一致；在发布侧修正之前每次核对都会重新下载`
    )
  }

  logger.info(`Runtime 已随本体更新到 ${pin.version}`)
  options.onProgress?.({ progress: 100, message: `Runtime 已更新到 ${pin.version}` })
  return { status: 'upgraded', pin }
}

// ==================== 给人看的失败原因 ====================

/** 下载失败：告诉用户先做什么、实在不行怎么手动补上。 */
function describeDownloadFailure(
  pin: RuntimeBinaryPin,
  runtimePath: string,
  detail: string
): string {
  const manual = buildRuntimeBinarySources(pin.version)[0].url
  return (
    `没能下载到本版本需要的 Runtime ${pin.version}（${detail}）。` +
    `请检查网络后重试；如果多次都不行，可以手动下载 ${manual} ，` +
    `重命名为 ${path.basename(runtimePath)} 后放到 ${path.dirname(runtimePath)} 覆盖原文件。`
  )
}

/** 替换失败：占用与权限是仅有的两种现实原因，给出对应的手动解法。 */
function describeReplaceFailure(runtimePath: string, error: unknown): string {
  const code = (error as NodeJS.ErrnoException)?.code
  const detail = error instanceof Error ? error.message : String(error)
  if (code === 'EBUSY' || code === 'EPERM' || code === 'EACCES') {
    return (
      `Runtime 文件正被占用或没有写入权限，无法替换 ${runtimePath}（${detail}）。` +
      `请在任务管理器里结束所有 auto-mas-runtime.exe 进程、关闭其它 AUTO-MAS 窗口后重试；` +
      `如果安全软件锁定了这个文件，请先把它放行。`
    )
  }
  return `替换 ${runtimePath} 失败（${detail}），请重试；仍然失败时请带上日志反馈。`
}

/** 新文件跑不起来之后原文件的下落：已换回 / 仍在 `.old` 里等下次启动恢复 / 本来就没有。 */
type BackupOutcome = 'restored' | 'kept' | 'none'

/** 新文件挪进来了却跑不起来。 */
function describeUnrunnableReplacement(
  pin: RuntimeBinaryPin,
  runtimePath: string,
  backup: BackupOutcome
): string {
  const tail = {
    restored: '已恢复原来的文件。',
    kept: `原来的文件仍保留在 ${runtimePath}${BACKUP_SUFFIX}，下次启动会自动换回。`,
    none: `原来的文件已不在，${path.basename(runtimePath)} 现在是新下载的那份。`,
  }[backup]
  return (
    `下载到的 Runtime ${pin.version} 校验无误但无法运行（${runtimePath}），${tail}` +
    `请检查安全软件是否拦截了它，放行后重试。`
  )
}

/** 钉扎取不到：只剩网络这一种原因。 */
function describePinUnavailable(version: string, detail: string): string {
  return (
    `无法确认 ${version} 需要的 Runtime 版本：CNB 与 GitHub 都没有给出结果（${detail}）。` +
    `请检查网络后重试；如果开了代理或安全软件，请确认没有拦截 cnb.cool 与 raw.githubusercontent.com。`
  )
}

// ==================== 下载 ====================

type DownloadOutcome =
  | { status: 'downloaded'; downloadPath: string }
  | { status: 'failed'; error: string }
  | { status: 'cancelled' }

/**
 * 先从可信来源拿到期望哈希，再逐个源下 exe 并比对；任一源拿到正确文件即返回该文件的路径。
 * exe 下载失败、对不上哈希，都只是换下一个源；拿不到可信哈希则一个源都不试。
 */
async function downloadPinned(
  pin: RuntimeBinaryPin,
  runtimePath: string,
  options: RuntimeBinarySyncOptions
): Promise<DownloadOutcome> {
  const download = options.download ?? defaultDownload
  const isCancelled = options.isCancelled ?? (() => false)
  const asset = runtimeAssetName(pin.version)
  const sources = buildRuntimeBinarySources(pin.version)
  const failures: string[] = []
  const deadline = Date.now() + (options.budgetMs ?? RUNTIME_BINARY_SYNC_BUDGET_MS)
  const sourceTimeoutMs = options.sourceTimeoutMs ?? RUNTIME_BINARY_SOURCE_TIMEOUT_MS

  // 第一步：可信来源的校验清单。它的进度不往上报——几十字节瞬间到 100% 再回到 0 只会让界面跳动。
  options.onProgress?.({ progress: 0, message: `正在获取 Runtime ${pin.version} 的校验信息` })
  const trusted = await fetchTrustedRuntimeHash(pin.version, {
    fetchText: options.fetchText,
    timeoutMs: Math.min(Math.max(deadline - Date.now(), 1), RUNTIME_TEXT_FETCH_TIMEOUT_MS),
  })
  if (trusted.status === 'unavailable') {
    return { status: 'failed', error: `无法从 CNB / GitHub 获取校验清单（${trusted.error}）` }
  }
  const expected = trusted.hash

  const budgetExhausted = (): boolean => {
    if (deadline - Date.now() > 0) return false
    failures.push('已用满本轮时间预算，剩余下载源不再尝试')
    logger.warn('Runtime 下载已用满时间预算，本轮放弃')
    return true
  }

  // 第二步：exe 本体，来源不限；对不上可信哈希的一律丢掉。
  for (const [index, source] of sources.entries()) {
    if (isCancelled()) return { status: 'cancelled' }
    if (budgetExhausted()) break

    const label = `${source.name}（${index + 1}/${sources.length}）`
    const message = `正在从 ${label} 下载 Runtime ${pin.version}`
    options.onProgress?.({ progress: 0, message, item: asset, source: source.key })

    logger.info(`尝试从 ${label} 下载 Runtime ${pin.version}: ${source.url}`)
    const downloadPath = nextDownloadPath(runtimePath)
    const result = await downloadWithTimeout(
      download,
      source.url,
      downloadPath,
      Math.min(deadline - Date.now(), sourceTimeoutMs),
      progress =>
        options.onProgress?.({
          progress: progress.progress,
          message,
          item: asset,
          source: source.key,
          bytesPerSecond: progress.speed,
          current: progress.downloadedSize,
          total: progress.totalSize,
        }),
      isCancelled
    )
    if (result.cancelled) return { status: 'cancelled' }
    if (!result.success) {
      failures.push(`${source.name}: ${result.error}`)
      // 超时放弃的那次仍在后台写自己的文件，等它自己结束时再清；这里删了也会被写回来。
      if (!result.abandoned) removeQuietly(downloadPath)
      continue
    }

    const actual = await hashFileSha256(downloadPath)
    if (actual === expected) {
      if (isCancelled()) {
        removeQuietly(downloadPath)
        return { status: 'cancelled' }
      }
      return { status: 'downloaded', downloadPath }
    }

    // 与可信清单对不上：该源缓存错乱、被篡改或返回了错误页，只能换下一个源。
    failures.push(`${source.name}: SHA-256 不匹配（清单 ${expected}，得到 ${actual ?? '不可读'}）`)
    logger.warn(`${label} 下载的文件与可信清单不符，换下一个源`)
    removeQuietly(downloadPath)
  }

  return { status: 'failed', error: `${sources.length} 个下载源均失败 —— ${failures.join('；')}` }
}

let downloadSequence = 0

/** 每次尝试各用一个临时文件名，理由见 {@link DOWNLOAD_SUFFIX}。 */
function nextDownloadPath(runtimePath: string): string {
  downloadSequence += 1
  const token = `${Date.now().toString(36)}-${downloadSequence.toString(36)}`
  return `${runtimePath}${DOWNLOAD_SUFFIX}-${token}`
}

/** 取消判据的轮询间隔：下载器没有取消接口，只能在等它的同时定期问一次调用方。 */
const CANCEL_POLL_INTERVAL_MS = 250

interface AttemptResult {
  success: boolean
  error?: string
  /** 超时或取消后放弃了这次下载：它仍在后台写文件，结束后由这里顺手清掉。 */
  abandoned?: boolean
  cancelled?: boolean
}

/**
 * 给一次下载加时长上限与取消判据。
 *
 * 下载器没有取消接口，超时或取消后只是不再等它：在途的那次会继续把数据写进 `savePath`，
 * 跑完后才由这里顺手删掉；它的进度也不再往上报，免得界面上出现两个源的进度交错跳动。
 */
async function downloadWithTimeout(
  download: RuntimeBinaryDownloader,
  url: string,
  savePath: string,
  timeoutMs: number,
  onProgress: (progress: RuntimeBinaryDownloadProgress) => void,
  isCancelled: () => boolean
): Promise<AttemptResult> {
  let abandoned = false
  let attempt: ReturnType<RuntimeBinaryDownloader>
  try {
    attempt = download(url, savePath, progress => {
      if (!abandoned) onProgress(progress)
    })
  } catch (error) {
    return { success: false, error: error instanceof Error ? error.message : String(error) }
  }
  const settled: Promise<AttemptResult> = attempt.then(
    result => (result.success ? result : { success: false, error: result.error ?? '下载失败' }),
    error => ({ success: false, error: error instanceof Error ? error.message : String(error) })
  )

  let timer: ReturnType<typeof setTimeout> | undefined
  let poller: ReturnType<typeof setInterval> | undefined
  const timeout = new Promise<AttemptResult>(resolve => {
    timer = setTimeout(() => {
      resolve({
        success: false,
        abandoned: true,
        error: `超过 ${Math.ceil(timeoutMs / 1000)} 秒仍未下载完成，放弃该源`,
      })
    }, timeoutMs)
    timer.unref?.()
  })
  const cancel = new Promise<AttemptResult>(resolve => {
    poller = setInterval(() => {
      if (isCancelled())
        resolve({ success: false, abandoned: true, cancelled: true, error: '已取消' })
    }, CANCEL_POLL_INTERVAL_MS)
    poller.unref?.()
  })

  try {
    const result = await Promise.race([settled, timeout, cancel])
    if (result.abandoned) {
      abandoned = true
      logger.warn(
        `${url} 下载${result.cancelled ? '已取消' : '超时'}，不再等它；在途的下载结束后会清掉 ${savePath}`
      )
      void settled.then(() => removeQuietly(savePath))
    }
    return result
  } finally {
    if (timer) clearTimeout(timer)
    if (poller) clearInterval(poller)
  }
}

/** 清掉上次留下的全部半截下载（任意 token）。备份 `.old` 不在这里清，见 {@link runSync}。 */
function removeStaleDownloads(runtimePath: string): void {
  const directory = path.dirname(runtimePath)
  const basename = path.basename(runtimePath)
  let entries: string[]
  try {
    entries = fs.readdirSync(directory)
  } catch {
    return
  }
  for (const entry of entries) {
    if (entry.startsWith(`${basename}${DOWNLOAD_SUFFIX}`)) {
      removeQuietly(path.join(directory, entry))
    }
  }
}

/**
 * 换成新文件，旧文件留作备份。
 *
 * 一律两步走：先把旧文件改名为 `<exe>.old` 让路（正在运行的 exe 不能被覆盖，但可以被改名），
 * 再把新文件挪到正式路径。不直接覆盖，是因为覆盖之后旧文件就没了——新文件万一在这台机器上
 * 跑不起来（安全软件拦截），用户手里就一个能用的都不剩；有备份在，调用方确认新文件能运行
 * 后再清掉它，跑不起来就换回去。
 *
 * 两步之间断电会留下「目录里只有 `.old`」的状态，由定位 exe 的 `resolveRuntimeExecutable()`
 * 在下次启动时把备份改回来（`recoverRuntimeBackup`），不需要人工干预。
 *
 * 新文件挪不进去时把旧文件改回来；连改回来都失败就保留 `.old`，错误照原样抛给调用方，
 * 下次定位 exe 时会再试一次恢复。返回是否留下了备份（旧文件本来就不存在时为 false）。
 */
function replaceRuntimeBinary(
  runtimePath: string,
  downloadPath: string,
  backupPath: string
): boolean {
  const hadExisting = fs.existsSync(runtimePath)
  const hadBackup = fs.existsSync(backupPath)
  let discarded: string | null = null
  if (hadExisting && hadBackup) {
    // 备份还在，说明现在这份 exe 已经被判定跑不起来、且换不回去：它不配当备份，按半截
    // 下载的命名挪开（挪不走就清不掉，下次当残留再清），别拿它覆盖最后一份能跑的。
    discarded = nextDownloadPath(runtimePath)
    fs.renameSync(runtimePath, discarded)
  } else if (hadExisting) {
    fs.renameSync(runtimePath, backupPath)
  }

  try {
    fs.renameSync(downloadPath, runtimePath)
  } catch (error) {
    if (hadExisting || hadBackup) restoreBackup(runtimePath, backupPath)
    if (discarded) removeQuietly(discarded)
    throw error
  }
  if (discarded) removeQuietly(discarded)
  return hadExisting || hadBackup
}

/** 把备份改回正式路径；成功返回 true，失败时保留备份供下次启动恢复。 */
function restoreBackup(runtimePath: string, backupPath: string): boolean {
  removeQuietly(runtimePath)
  try {
    fs.renameSync(backupPath, runtimePath)
    return true
  } catch (error) {
    logger.error(
      `恢复 ${backupPath} 失败，保留备份等下次启动再试: ${
        error instanceof Error ? error.message : String(error)
      }`
    )
    return false
  }
}

/** 删不掉就算了：残留文件会在下一次同步开始时再清一遍。 */
function removeQuietly(target: string): void {
  try {
    fs.rmSync(target, { force: true })
  } catch {
    // 忽略：文件可能仍被占用，不影响本次结果。
  }
}

// ==================== 第 0 步：按目标版本对齐 ====================

export const RUNTIME_PIN_UNAVAILABLE = 'RUNTIME_PIN_UNAVAILABLE'
/** 第 0 步自己抛了异常（不该发生）：编排器用它把这种失败也归到「整条重来」。 */
export const RUNTIME_BINARY_ALIGN_ERROR = 'RUNTIME_BINARY_ALIGN_ERROR'

export type RuntimeBinaryAlignStatus = RuntimeBinarySyncStatus | 'unpinned'

export interface RuntimeBinaryAlignResult {
  /**
   * 在 {@link RuntimeBinarySyncResult} 的五种之上多一种 `unpinned`：目标发布分支上没有
   * 钉扎文件（该版本发布时还没有这个机制），什么都不做。
   */
  status: RuntimeBinaryAlignStatus
  pin?: RuntimeBinaryPin
  /** 钉扎来自哪个来源的 key（`cnb` / `github`）。 */
  pinSource?: string
  /** 给用户看的一句话。 */
  error?: string
  code?: string
}

export interface RuntimeBinaryAlignOptions {
  /** 目标版本（`v` 开头），决定去哪条发布分支读钉扎。 */
  version: string
  runtimePath: string
  appRoot: string
  onProgress?: (progress: RuntimeBinarySyncProgress) => void
  isCancelled?: () => boolean
  /** 测试注入。 */
  fetchPin?: (version: string) => Promise<RemoteRuntimePinLookup>
  sync?: (options: RuntimeBinarySyncOptions) => Promise<RuntimeBinarySyncResult>
}

/**
 * 第 0 步：在 bootstrap 之前，把 Runtime 对齐到目标版本的发布分支所钉扎的那一版。
 *
 * 钉扎从远端读而不是本地 `repo/`：首次安装时 `repo/` 还不存在，更新时它里面是旧版本的
 * 钉扎——两种情形下本地都没有「目标版本要什么」这个答案。读到钉扎后与 exe 自报的版本
 * 比对，不一致就下载替换；这一步做完，接下来克隆源码的才是配套的 Runtime。
 *
 * 钉扎取不到按失败返回（`RUNTIME_PIN_UNAVAILABLE`），理由见模块头。开发者自带的 Runtime
 * （`AUTO_MAS_RUNTIME_EXE`）连钉扎都不读：读了也不会替换，没必要为它联一次网。
 */
export async function alignRuntimeBinaryWithVersion(
  options: RuntimeBinaryAlignOptions
): Promise<RuntimeBinaryAlignResult> {
  const { version, runtimePath, appRoot } = options

  if (isDeveloperRuntime(runtimePath)) {
    logger.info(`${RUNTIME_EXE_ENV} 指定了 Runtime，第 0 步跳过`)
    return { status: 'skipped' }
  }

  options.onProgress?.({ progress: 0, message: `正在确认 ${version} 需要的 Runtime 版本` })
  const lookup = await (options.fetchPin ?? fetchRemoteRuntimeBinaryPin)(version)
  if (lookup.status === 'unpinned') return { status: 'unpinned' }
  if (lookup.status === 'unavailable') {
    const error = describePinUnavailable(version, lookup.error)
    logger.warn(error)
    return { status: 'failed', error, code: RUNTIME_PIN_UNAVAILABLE }
  }
  if (options.isCancelled?.()) {
    return {
      status: 'cancelled',
      pin: lookup.pin,
      pinSource: lookup.source,
      code: RUNTIME_BINARY_CANCELLED,
    }
  }

  const outcome = await (options.sync ?? syncRuntimeBinary)({
    runtimePath,
    appRoot,
    pin: lookup.pin,
    onProgress: options.onProgress,
    isCancelled: options.isCancelled,
  })
  return { ...outcome, pinSource: lookup.source }
}
