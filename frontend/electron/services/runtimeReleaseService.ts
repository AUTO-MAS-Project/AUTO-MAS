/**
 * Runtime 线上最新版本解析
 *
 * Runtime 有自己的发布节奏：修复版发布后，用户是否用上它不该取决于本体是否发版。这里从
 * 项目自己控制的 CNB / GitHub Release 列表里解析线上最新版本，供完整初始化链路把
 * `auto-mas-runtime.exe` 对齐到最新版；安装包内置的版本（`res/runtime-version.txt`）只由
 * 构建 CI 与本地打包脚本读取，运行时不再用它。
 *
 * 几条刻意的取舍：
 *
 * - **只认项目自己控制的来源。** CNB 优先（国内直连、无频率限制），GitHub 兜底（官方 API，
 *   匿名每 IP 每小时 60 次，只兜底用）。两者都与下载物、校验清单同属项目控制域。
 * - **按语义版本取最大，不用 `/releases/latest`。** 后者按发布时间排序，也不排除 beta tag；
 *   仓库里 Python 侧的 GitHub 版本检查（`app/task/MaaFW/.../updater.py`）已经踩过并留下注释。
 * - **通道跟随本体。** 本体是正式版时只取正式版 Runtime；本体是预发布版时同时接受 Runtime
 *   预发布版（正式版当然也接受）。Runtime 预发布只是给公测用户提前验证，正式版用户不该拿到。
 * - **解析结果进程内缓存，失败不缓存。** 一次完整初始化里第 0 步、重试、失败页核对可能连续
 *   触发，不能每次都打一遍接口；失败要让下一次重试真的重新联网。
 */

import { getLogger } from './logger'

const logger = getLogger('Runtime版本')

/** Runtime 发布仓库：GitHub 是原件，CNB 是每次发布同步过去的官方镜像。 */
export const RUNTIME_RELEASE_REPO = 'AUTO-MAS-Project/AUTO-MAS-Runtime'

/**
 * Runtime 版本号的合法形态：`v` 加点分数字，可跟一段预发布/构建后缀。
 *
 * 与发布 CI、本地打包脚本和 `runtimeUpdateService` 里那条同源——版本号会被拼进下载 URL，
 * 带 `/` 或空白的值必须在这里挡掉。
 */
export const RUNTIME_VERSION_PATTERN = /^v\d+(\.\d+)*([-+][0-9A-Za-z.-]+)?$/

/**
 * 只取最近一页。
 *
 * 最新版只会在列表最前面，一页 20 条足够覆盖「连续多个预发布版本」的窗口；再往后翻没有意义，
 * 也避免为了找一个更旧的版本反复请求。
 */
const RELEASE_PAGE_SIZE = 20

/** Release 列表的响应体上限：20 条元数据不到 200 KiB，超过说明读到的不是它。 */
const MAX_RELEASE_LIST_BYTES = 1024 * 1024

/** 单个来源的时长上限：列表是固定大小的静态响应，超时就是这条来源不通。 */
export const RUNTIME_RELEASE_FETCH_TIMEOUT_MS = 8 * 1000

/** 解析成功的缓存时长。失败不缓存，重试会重新联网。 */
export const RUNTIME_RELEASE_CACHE_TTL_MS = 5 * 60 * 1000

/** Runtime 发布通道：跟随本体是正式版还是预发布版。 */
export type RuntimeReleaseChannel = 'stable' | 'prerelease'

/**
 * 本体版本决定 Runtime 通道。
 *
 * 本体带预发布后缀（`5.7.0-beta.5` / `-rc.1`）时才接受 Runtime 预发布版；正式版本体只认
 * Runtime 正式版，避免把只在公测里验证过的 Runtime 推给正式用户。
 */
export function resolveRuntimeReleaseChannel(appVersion: string): RuntimeReleaseChannel {
  return /-[0-9A-Za-z]/.test(appVersion.trim()) ? 'prerelease' : 'stable'
}

/** 一个 Release 列表来源。 */
export interface RuntimeReleaseSource {
  key: string
  name: string
  url: string
  headers: Record<string, string>
}

/**
 * Release 列表的两个来源，按尝试顺序排列。
 *
 * CNB 的公开列表端点是站点自身在用的 JSON 接口（带 `Accept: application/vnd.cnb.api+json`
 * 才回 JSON，否则回 HTML 页面），匿名可读、没有频率限制；GitHub 是官方 REST API。
 */
export function buildRuntimeReleaseSources(): RuntimeReleaseSource[] {
  return [
    {
      key: 'cnb',
      name: 'CNB',
      url: `https://cnb.cool/${RUNTIME_RELEASE_REPO}/-/releases?page_size=${RELEASE_PAGE_SIZE}`,
      headers: { Accept: 'application/vnd.cnb.api+json' },
    },
    {
      key: 'github',
      name: 'GitHub',
      url: `https://api.github.com/repos/${RUNTIME_RELEASE_REPO}/releases?per_page=${RELEASE_PAGE_SIZE}`,
      // GitHub API 强制要求 User-Agent，缺了会 403；与仓库里 Python 侧一致用同一个标识。
      headers: { Accept: 'application/vnd.github+json', 'User-Agent': 'AutoMasGui' },
    },
  ]
}

/** 列表里一条 Release 里我们关心的字段。两个来源同名，可以共用解析。 */
interface RuntimeReleaseEntry {
  tagName: string
  draft: boolean
  prerelease: boolean
}

function asRecord(value: unknown): Record<string, unknown> | undefined {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : undefined
}

/**
 * 把 Release 列表正文解析成条目；不是数组、或一个条目都不是对象时返回 null。
 *
 * 只做结构归一，不在这里筛版本：筛选规则集中在 {@link selectLatestRuntimeVersion}。
 */
export function parseRuntimeReleaseList(text: string): RuntimeReleaseEntry[] | null {
  let decoded: unknown
  try {
    decoded = JSON.parse(text)
  } catch {
    return null
  }
  if (!Array.isArray(decoded)) return null

  const entries: RuntimeReleaseEntry[] = []
  for (const item of decoded) {
    const record = asRecord(item)
    if (!record) continue
    const tagName = typeof record.tag_name === 'string' ? record.tag_name.trim() : ''
    if (!tagName) continue
    entries.push({
      tagName,
      draft: record.draft === true,
      prerelease: record.prerelease === true,
    })
  }
  return entries.length > 0 ? entries : null
}

/**
 * 比较两个 Runtime 版本号：`target` 是否比 `installed` 新。
 *
 * 只用于「要不要升级」与「列表里选最大」；版本号都先过 {@link RUNTIME_VERSION_PATTERN}。
 * 规则按 semver：数字段逐段比较，预发布段缺失者更大，数字标识小于字母标识，构建元数据忽略。
 */
export function isNewerRuntimeVersion(target: string, installed: string): boolean {
  const parse = (value: string) => {
    const [core, prerelease] = value.replace(/^v/, '').split('+')[0].split(/-(.*)/)
    return { numbers: core.split('.').map(Number), prerelease }
  }
  const next = parse(target)
  const current = parse(installed)
  for (let index = 0; index < Math.max(next.numbers.length, current.numbers.length); index++) {
    const difference = (next.numbers[index] ?? 0) - (current.numbers[index] ?? 0)
    if (difference !== 0) return difference > 0
  }
  if (next.prerelease === current.prerelease) return false
  if (!next.prerelease) return true
  if (!current.prerelease) return false
  const nextParts = next.prerelease.split('.')
  const currentParts = current.prerelease.split('.')
  for (let index = 0; index < Math.max(nextParts.length, currentParts.length); index++) {
    const left = nextParts[index]
    const right = currentParts[index]
    if (left === right) continue
    if (left === undefined) return false
    if (right === undefined) return true
    const leftNumeric = /^\d+$/.test(left)
    const rightNumeric = /^\d+$/.test(right)
    if (leftNumeric && rightNumeric) return Number(left) > Number(right)
    if (leftNumeric !== rightNumeric) return !leftNumeric
    return left > right
  }
  return false
}

/**
 * 从列表里选出通道内最新的版本号；没有合法条目时返回 null。
 *
 * 过滤顺序：草稿 → 版本号形态 → 通道（正式版通道同时挡掉 `prerelease` 标记与带 `-` 后缀的
 * tag，因为两个来源的标记不一定一致）。
 */
export function selectLatestRuntimeVersion(
  entries: readonly RuntimeReleaseEntry[],
  channel: RuntimeReleaseChannel
): string | null {
  let latest: string | null = null
  for (const entry of entries) {
    if (entry.draft) continue
    const version = entry.tagName
    if (!RUNTIME_VERSION_PATTERN.test(version)) continue
    if (channel === 'stable' && (entry.prerelease || version.includes('-'))) continue
    if (latest === null || isNewerRuntimeVersion(version, latest)) latest = version
  }
  return latest
}

/** 单个 Release 列表来源的抓取结果。 */
export type RuntimeReleaseFetchOutcome =
  | { kind: 'text'; text: string }
  | { kind: 'failed'; error: string; networkUnavailable?: true }

export type RuntimeReleaseFetcher = (
  source: RuntimeReleaseSource,
  timeoutMs: number
) => Promise<RuntimeReleaseFetchOutcome>

/** 默认抓取：跟随重定向，只认 2xx；超时、断网、非 2xx 都归为失败。 */
const defaultFetchRelease: RuntimeReleaseFetcher = async (source, timeoutMs) => {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), timeoutMs)
  try {
    const response = await fetch(source.url, {
      signal: controller.signal,
      headers: { ...source.headers, 'Cache-Control': 'no-cache' },
    })
    if (!response.ok) return { kind: 'failed', error: `HTTP ${response.status}` }
    const text = await response.text()
    if (text.length > MAX_RELEASE_LIST_BYTES) return { kind: 'failed', error: '返回的内容过大' }
    return { kind: 'text', text }
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error)
    return {
      kind: 'failed',
      error: controller.signal.aborted ? `${Math.ceil(timeoutMs / 1000)} 秒内没有响应` : message,
      networkUnavailable: true,
    }
  } finally {
    clearTimeout(timer)
  }
}

/** 线上最新版本的解析结局。 */
export type LatestRuntimeVersionLookup =
  | { status: 'resolved'; version: string; source: string }
  /** 两个来源都没有给出可用的版本：网络不通、返回了非列表内容，或列表里没有该通道的版本。 */
  | { status: 'unavailable'; error: string; networkUnavailable?: true }

export interface ResolveLatestRuntimeVersionOptions {
  channel: RuntimeReleaseChannel
  timeoutMs?: number
  /** 测试注入；默认用全局 `fetch`。 */
  fetchRelease?: RuntimeReleaseFetcher
}

/**
 * 解析线上最新 Runtime 版本。
 *
 * 按 {@link buildRuntimeReleaseSources} 的顺序逐个尝试：先拿到的合法结果即为答案（CNB 优先），
 * 前一个来源失败才轮到下一个。全部失败时，只有**每个**来源都是网络层失败才标
 * `networkUnavailable`——「列表里没有正式版」这种明确结论不该被当成断网。
 */
export async function resolveLatestRuntimeVersion(
  options: ResolveLatestRuntimeVersionOptions
): Promise<LatestRuntimeVersionLookup> {
  const { channel } = options
  const fetchRelease = options.fetchRelease ?? defaultFetchRelease
  const timeoutMs = options.timeoutMs ?? RUNTIME_RELEASE_FETCH_TIMEOUT_MS
  const sources = buildRuntimeReleaseSources()
  const failures: string[] = []
  let networkFailureCount = 0

  for (const source of sources) {
    logger.debug(`从 ${source.name} 读取 Runtime 发布列表: ${source.url}`)
    let outcome: RuntimeReleaseFetchOutcome
    try {
      outcome = await fetchRelease(source, timeoutMs)
    } catch (error) {
      outcome = {
        kind: 'failed',
        error: error instanceof Error ? error.message : String(error),
      }
    }

    if (outcome.kind === 'text') {
      const entries = parseRuntimeReleaseList(outcome.text)
      if (entries) {
        const version = selectLatestRuntimeVersion(entries, channel)
        if (version) {
          logger.info(`${source.name} 上的最新 Runtime 是 ${version}`)
          return { status: 'resolved', version, source: source.key }
        }
        failures.push(
          `${source.name}: 列表里没有可用的${channel === 'stable' ? '正式版' : '发布版'} Runtime`
        )
      } else {
        failures.push(`${source.name}: 返回的内容不是 Release 列表`)
      }
      continue
    }

    failures.push(`${source.name}: ${outcome.error}`)
    if (outcome.networkUnavailable) networkFailureCount += 1
  }

  const error = failures.join('；')
  logger.warn(`没能确认线上最新的 Runtime 版本: ${error}`)
  return {
    status: 'unavailable',
    error,
    ...(networkFailureCount === sources.length ? { networkUnavailable: true as const } : {}),
  }
}

/** 缓存下来的解析结果。 */
interface LatestRuntimeVersionCacheEntry {
  channel: RuntimeReleaseChannel
  version: string
  source: string
  resolvedAt: number
}

let cache: LatestRuntimeVersionCacheEntry | null = null
let inFlight: {
  channel: RuntimeReleaseChannel
  promise: Promise<LatestRuntimeVersionLookup>
} | null = null

/** 仅供测试清场。 */
export function resetLatestRuntimeVersionCache(): void {
  cache = null
  inFlight = null
}

/**
 * 与 {@link resolveLatestRuntimeVersion} 相同，但结果在进程内缓存 {@link RUNTIME_RELEASE_CACHE_TTL_MS}；
 * 同一通道的并发调用共用一次请求。
 */
export function resolveLatestRuntimeVersionCached(
  options: ResolveLatestRuntimeVersionOptions
): Promise<LatestRuntimeVersionLookup> {
  const { channel } = options
  if (
    cache &&
    cache.channel === channel &&
    Date.now() - cache.resolvedAt < RUNTIME_RELEASE_CACHE_TTL_MS
  ) {
    return Promise.resolve({ status: 'resolved', version: cache.version, source: cache.source })
  }
  if (inFlight && inFlight.channel === channel) return inFlight.promise

  const promise = resolveLatestRuntimeVersion(options)
    .then(result => {
      if (result.status === 'resolved') {
        cache = {
          channel,
          version: result.version,
          source: result.source,
          resolvedAt: Date.now(),
        }
      }
      return result
    })
    .finally(() => {
      if (inFlight?.promise === promise) inFlight = null
    })
  inFlight = { channel, promise }
  return promise
}
