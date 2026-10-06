import * as crypto from 'crypto'
import * as fs from 'fs'
import * as path from 'path'
import {
  APPEARANCE_LIMITS,
  AppearanceError,
  getAppearance,
  getAppearanceRoot,
  importAppearancePackage,
  inspectAppearancePackage,
} from './appearanceService'

// 与 src/types/appearance.ts 的 OnlineAppearance* 同形；主进程不能 import src/，在此自行声明。
type AppearanceMode = 'light' | 'dark'
type OnlineAppearanceErrorCode =
  | 'NETWORK'
  | 'NOT_FOUND'
  | 'BAD_RESPONSE'
  | 'TOO_LARGE'
  | 'CHECKSUM_MISMATCH'
  | 'EXPIRED'
  | 'UNSUPPORTED'
type AppearanceImportResult = ReturnType<typeof importAppearancePackage>
type AppearanceManifest = ReturnType<typeof inspectAppearancePackage>['manifest']

export interface OnlineAppearanceInstalled {
  appearanceId: string
  versionNo: number
}

export interface OnlineAppearanceItem {
  fileKey: string
  displayName: string
  description: string
  ownerUsername: string
  publishedVersionNo: number | null
  publishedAt: string
  updatedAt: string
  installed: OnlineAppearanceInstalled | null
}

export interface OnlineAppearanceVersion {
  versionNo: number
  fileSize: number
  sha256: string
  changeNote: string
  createdAt: string
}

export interface OnlineAppearanceQuery {
  page?: number
  pageSize?: number
  keyword?: string
}

export interface OnlineAppearanceListResult {
  success: boolean
  items?: OnlineAppearanceItem[]
  pagination?: { page: number; pageSize: number; total: number; hasNext: boolean }
  code?: OnlineAppearanceErrorCode
  error?: string
}

export interface OnlineAppearanceDetailResult {
  success: boolean
  item?: OnlineAppearanceItem
  versions?: OnlineAppearanceVersion[]
  code?: OnlineAppearanceErrorCode
  error?: string
}

export interface OnlineAppearancePreview {
  id: string
  name: string
  description?: string
  mode: AppearanceMode
  tokens: AppearanceManifest['tokens']
  previewUrl?: string
}

export interface OnlineAppearancePrepareResult {
  success: boolean
  token?: string
  fileKey?: string
  versionNo?: number
  fileSize?: number
  sha256?: string
  appearance?: OnlineAppearancePreview
  existing?: { id: string; name: string } | null
  code?: OnlineAppearanceErrorCode | 'INVALID_PACKAGE'
  error?: string
}

export interface OnlineAppearanceInstallResult extends Omit<AppearanceImportResult, 'code'> {
  code?: AppearanceImportResult['code'] | OnlineAppearanceErrorCode
}

/** 外观来源记录：与 theme.json 分开存放，装好的外观目录不允许出现未声明文件。 */
export interface AppearanceSourceRecord {
  origin: string
  projectKey: string
  categoryKey: string
  fileKey: string
  versionNo: number
  sha256: string
  installedAt: string
}

interface BodyReader {
  read(): Promise<{ done: boolean; value?: Uint8Array }>
  cancel(reason?: unknown): Promise<void>
}

/** fetch 实现只需满足这些字段；正式环境注入 Electron net.fetch，测试注入全局 fetch。 */
export interface OnlineResponseLike {
  status: number
  url: string
  headers: { get(name: string): string | null }
  body: { getReader(): BodyReader; cancel?(reason?: unknown): Promise<void> } | null
}

export type OnlineFetch = (
  url: string,
  init: { signal: AbortSignal; headers: Record<string, string> }
) => Promise<OnlineResponseLike>

export interface OnlineAppearanceLogger {
  info(message: string): void
  warn(message: string): void
}

export interface OnlineAppearanceServiceOptions {
  fetch: OnlineFetch
  userDataPath: () => string
  /** 只放本功能临时包的专用目录。 */
  cacheDir: () => string
  logger?: OnlineAppearanceLogger
  baseUrl?: string
  projectKey?: string
  categoryKey?: string
  metadataBytes?: number
  metadataTimeoutMs?: number
  downloadIdleTimeoutMs?: number
  cacheEntries?: number
  cacheTtlMs?: number
  now?: () => number
}

export const ONLINE_APPEARANCE_DEFAULTS = {
  baseUrl: 'https://data.auto-mas.top/api/v1',
  projectKey: 'auto-mas',
  categoryKey: 'Appearance',
  metadataBytes: 1024 * 1024,
  metadataTimeoutMs: 15_000,
  downloadIdleTimeoutMs: 30_000,
  cacheEntries: 4,
  cacheTtlMs: 30 * 60 * 1000,
} as const

export const APPEARANCE_SOURCES_FILE = 'appearance-sources.json'

const SHA256_HEX = /^[0-9a-f]{64}$/i
const APPEARANCE_ID = /^[a-z0-9][a-z0-9_-]{0,63}$/
const CACHE_FILE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\.(?:zip|part)$/i

class OnlineAppearanceError extends Error {
  readonly code: OnlineAppearanceErrorCode

  constructor(code: OnlineAppearanceErrorCode, message: string) {
    super(message)
    this.name = 'OnlineAppearanceError'
    this.code = code
  }
}

const NO_LOGGER: OnlineAppearanceLogger = { info: () => undefined, warn: () => undefined }

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error)
}

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
}

function clipText(value: unknown, maxLength: number): string {
  if (typeof value !== 'string') return ''
  const chars = Array.from(value)
  return chars.length > maxLength ? chars.slice(0, maxLength).join('') : value
}

function positiveInteger(value: unknown): number | null {
  return typeof value === 'number' && Number.isSafeInteger(value) && value > 0 ? value : null
}

function hasControlChar(value: string): boolean {
  return [...value].some(char => char.charCodeAt(0) < 0x20 || char === '\u007f')
}

/** 分享站 file_key 只用作 URL 段，拒绝任何能改变路径或查询的字符。 */
export function isValidOnlineFileKey(value: unknown): value is string {
  return (
    typeof value === 'string' &&
    value.length > 0 &&
    value.length <= 128 &&
    value !== '.' &&
    value !== '..' &&
    !/[/\\?#%]/.test(value) &&
    !hasControlChar(value)
  )
}

function removeQuietly(filePath: string): void {
  try {
    fs.rmSync(filePath, { force: true })
  } catch {
    // 缓存清理失败不影响结果；下次注册时会再清一次专用目录。
  }
}

// ==================== 来源记录 ====================

function sourcesPath(userDataPath: string): string {
  return path.join(userDataPath, APPEARANCE_SOURCES_FILE)
}

function normalizeSourceRecord(value: unknown): AppearanceSourceRecord | null {
  if (!isPlainObject(value)) return null
  const { origin, projectKey, categoryKey, fileKey, versionNo, sha256, installedAt } = value
  if (
    typeof origin !== 'string' ||
    typeof projectKey !== 'string' ||
    typeof categoryKey !== 'string' ||
    !isValidOnlineFileKey(fileKey) ||
    positiveInteger(versionNo) === null ||
    typeof sha256 !== 'string' ||
    !SHA256_HEX.test(sha256) ||
    typeof installedAt !== 'string'
  ) {
    return null
  }
  return {
    origin,
    projectKey,
    categoryKey,
    fileKey,
    versionNo: versionNo as number,
    sha256: sha256.toLowerCase(),
    installedAt,
  }
}

/** 读取来源记录；文件缺失按空处理，损坏时记 warn 后按空处理。 */
export function readAppearanceSources(
  userDataPath: string,
  logger: OnlineAppearanceLogger = NO_LOGGER
): Record<string, AppearanceSourceRecord> {
  const filePath = sourcesPath(userDataPath)
  let raw: string
  try {
    const stat = fs.statSync(filePath)
    if (!stat.isFile() || stat.size > ONLINE_APPEARANCE_DEFAULTS.metadataBytes) {
      logger.warn('外观来源记录无效，按空记录处理')
      return {}
    }
    raw = fs.readFileSync(filePath, 'utf8')
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code !== 'ENOENT') {
      logger.warn(`读取外观来源记录失败，按空记录处理: ${errorMessage(error)}`)
    }
    return {}
  }
  let parsed: unknown
  try {
    parsed = JSON.parse(raw.replace(/^\uFEFF/, ''))
  } catch (error) {
    logger.warn(`外观来源记录已损坏，按空记录处理: ${errorMessage(error)}`)
    return {}
  }
  if (!isPlainObject(parsed) || parsed.schemaVersion !== 1 || !isPlainObject(parsed.sources)) {
    logger.warn('外观来源记录格式不受支持，按空记录处理')
    return {}
  }
  const sources: Record<string, AppearanceSourceRecord> = {}
  for (const [id, value] of Object.entries(parsed.sources)) {
    const record = normalizeSourceRecord(value)
    if (APPEARANCE_ID.test(id) && record) sources[id] = record
  }
  return sources
}

function writeAppearanceSources(
  userDataPath: string,
  sources: Record<string, AppearanceSourceRecord>
): void {
  const filePath = sourcesPath(userDataPath)
  fs.mkdirSync(path.dirname(filePath), { recursive: true })
  const tempPath = `${filePath}.${process.pid}.${crypto.randomUUID()}.tmp`
  try {
    fs.writeFileSync(
      tempPath,
      `${JSON.stringify({ schemaVersion: 1, sources }, null, 2)}\n`,
      'utf8'
    )
    fs.renameSync(tempPath, filePath)
  } catch (error) {
    removeQuietly(tempPath)
    throw error
  }
}

export function setAppearanceSource(
  userDataPath: string,
  appearanceId: string,
  record: AppearanceSourceRecord,
  logger: OnlineAppearanceLogger = NO_LOGGER
): void {
  const sources = readAppearanceSources(userDataPath, logger)
  sources[appearanceId] = record
  writeAppearanceSources(userDataPath, sources)
}

/** 删除某个外观的来源记录；没有记录时不写文件。返回是否删掉了记录。 */
export function removeAppearanceSource(
  userDataPath: string,
  appearanceId: string,
  logger: OnlineAppearanceLogger = NO_LOGGER
): boolean {
  const sources = readAppearanceSources(userDataPath, logger)
  if (!Object.prototype.hasOwnProperty.call(sources, appearanceId)) return false
  delete sources[appearanceId]
  writeAppearanceSources(userDataPath, sources)
  return true
}

// ==================== 服务 ====================

interface CacheEntry {
  path: string
  fileKey: string
  versionNo: number
  sha256: string
  fileSize: number
  createdAt: number
  installing: boolean
}

export interface OnlineAppearanceService {
  list(query: OnlineAppearanceQuery): Promise<OnlineAppearanceListResult>
  detail(fileKey: unknown): Promise<OnlineAppearanceDetailResult>
  prepare(fileKey: unknown, versionNo: unknown): Promise<OnlineAppearancePrepareResult>
  install(token: unknown, replace: boolean): OnlineAppearanceInstallResult
  discard(token: unknown): { success: boolean }
  /** 清空专用缓存目录里本功能留下的 `<uuid>.zip` / `<uuid>.part`。 */
  clearCacheDirectory(): void
}

function failure<T extends { success: boolean }>(
  error: unknown,
  logger: OnlineAppearanceLogger
): T {
  if (error instanceof OnlineAppearanceError) {
    return { success: false, code: error.code, error: error.message } as unknown as T
  }
  if (error instanceof AppearanceError) {
    return { success: false, code: error.code, error: error.message } as unknown as T
  }
  logger.warn(`在线外观处理出错: ${errorMessage(error)}`)
  return { success: false, error: `处理在线外观时出错：${errorMessage(error)}` } as unknown as T
}

function invalidArgument<T>(message: string): T {
  return { success: false, error: message } as unknown as T
}

export function createOnlineAppearanceService(
  options: OnlineAppearanceServiceOptions
): OnlineAppearanceService {
  const settings = { ...ONLINE_APPEARANCE_DEFAULTS, ...stripUndefined(options) }
  const logger = options.logger ?? NO_LOGGER
  const fetchImpl = options.fetch
  const baseUrl = settings.baseUrl.replace(/\/+$/, '')
  const baseIsHttps = new URL(baseUrl).protocol === 'https:'
  const origin = new URL(baseUrl).origin
  const now = options.now ?? (() => Date.now())
  const cache = new Map<string, CacheEntry>()

  const fileUrl = (fileKey: string): string =>
    `${baseUrl}/files/${encodeURIComponent(settings.projectKey)}/${encodeURIComponent(
      settings.categoryKey
    )}/${encodeURIComponent(fileKey)}`

  const networkError = (timedOut: boolean, interrupted = false): OnlineAppearanceError =>
    new OnlineAppearanceError(
      'NETWORK',
      timedOut
        ? '连接分享站超时，请稍后重试'
        : interrupted
          ? '与分享站的连接中断，请检查网络后重试'
          : '无法连接分享站，请检查网络后重试'
    )

  const statusError = (status: number, notFound: string): OnlineAppearanceError => {
    if (status === 404) return new OnlineAppearanceError('NOT_FOUND', notFound)
    if (status >= 500) {
      return new OnlineAppearanceError('NETWORK', `分享站暂时不可用（HTTP ${status}），请稍后重试`)
    }
    return new OnlineAppearanceError('BAD_RESPONSE', `分享站返回了异常响应（HTTP ${status}）`)
  }

  const assertSecureResponse = (response: OnlineResponseLike): void => {
    if (!baseIsHttps) return
    let protocol = 'https:'
    try {
      if (response.url) protocol = new URL(response.url).protocol
    } catch {
      protocol = ''
    }
    if (protocol !== 'https:') {
      throw new OnlineAppearanceError('BAD_RESPONSE', '分享站被重定向到了不安全的地址，已拒绝')
    }
  }

  const cancelBody = (response: OnlineResponseLike | undefined): void => {
    try {
      void response?.body?.cancel?.().catch(() => undefined)
    } catch {
      // body 已被读取或锁定时 cancel 会抛错，无需处理。
    }
  }

  /** 元数据请求：限时、限大小，只接受 200 + `{code:0,data}` 信封。 */
  const requestJson = async (url: string, notFound: string): Promise<unknown> => {
    const controller = new AbortController()
    let timedOut = false
    const timer = setTimeout(() => {
      timedOut = true
      controller.abort()
    }, settings.metadataTimeoutMs)
    let response: OnlineResponseLike | undefined
    try {
      try {
        response = await fetchImpl(url, {
          signal: controller.signal,
          headers: { Accept: 'application/json' },
        })
      } catch {
        throw networkError(timedOut)
      }
      assertSecureResponse(response)
      if (response.status !== 200) throw statusError(response.status, notFound)
      if (!response.body) throw new OnlineAppearanceError('BAD_RESPONSE', '分享站返回了空响应')
      const reader = response.body.getReader()
      const chunks: Buffer[] = []
      let total = 0
      for (;;) {
        let chunk: { done: boolean; value?: Uint8Array }
        try {
          chunk = await reader.read()
        } catch {
          throw networkError(timedOut, true)
        }
        if (chunk.done) break
        if (!chunk.value) continue
        total += chunk.value.byteLength
        if (total > settings.metadataBytes) {
          void reader.cancel().catch(() => undefined)
          throw new OnlineAppearanceError('BAD_RESPONSE', '分享站返回的数据过大')
        }
        chunks.push(Buffer.from(chunk.value))
      }
      let envelope: unknown
      try {
        envelope = JSON.parse(
          Buffer.concat(chunks)
            .toString('utf8')
            .replace(/^\uFEFF/, '')
        )
      } catch {
        throw new OnlineAppearanceError('BAD_RESPONSE', '分享站返回的数据无法解析')
      }
      if (!isPlainObject(envelope) || envelope.code !== 0 || !('data' in envelope)) {
        throw new OnlineAppearanceError('BAD_RESPONSE', '分享站返回的数据格式不正确')
      }
      return envelope.data
    } catch (error) {
      cancelBody(response)
      controller.abort()
      throw error
    } finally {
      clearTimeout(timer)
    }
  }

  const installedFor = (
    fileKey: string,
    sources: Record<string, AppearanceSourceRecord>
  ): OnlineAppearanceInstalled | null => {
    let root: string
    try {
      root = getAppearanceRoot(options.userDataPath())
    } catch {
      return null
    }
    let best: { id: string; record: AppearanceSourceRecord; time: number } | undefined
    for (const [id, record] of Object.entries(sources)) {
      if (
        record.projectKey !== settings.projectKey ||
        record.categoryKey !== settings.categoryKey ||
        record.fileKey !== fileKey
      ) {
        continue
      }
      try {
        if (!fs.statSync(path.join(root, id, 'theme.json')).isFile()) continue
      } catch {
        continue
      }
      const parsedTime = Date.parse(record.installedAt)
      const time = Number.isFinite(parsedTime) ? parsedTime : Number.NEGATIVE_INFINITY
      if (!best || time > best.time) best = { id, record, time }
    }
    return best ? { appearanceId: best.id, versionNo: best.record.versionNo } : null
  }

  const mapItem = (
    raw: unknown,
    sources: Record<string, AppearanceSourceRecord>
  ): OnlineAppearanceItem | null => {
    if (!isPlainObject(raw) || !isValidOnlineFileKey(raw.file_key)) return null
    const fileKey = raw.file_key
    return {
      fileKey,
      displayName: clipText(raw.display_name, 120) || fileKey,
      description: clipText(raw.description, 2000),
      ownerUsername: clipText(raw.owner_username, 64),
      publishedVersionNo: positiveInteger(raw.published_version_no),
      publishedAt: clipText(raw.published_at, 64),
      updatedAt: clipText(raw.updated_at, 64),
      installed: installedFor(fileKey, sources),
    }
  }

  /** 单个版本字段不合法时丢弃该版本；版本号重复则整个列表视为异常。 */
  const mapVersions = (data: unknown, fileKey: string): OnlineAppearanceVersion[] => {
    if (!Array.isArray(data)) {
      throw new OnlineAppearanceError('BAD_RESPONSE', '分享站返回的版本列表格式不正确')
    }
    const versions: OnlineAppearanceVersion[] = []
    const seen = new Set<number>()
    let dropped = 0
    for (const raw of data) {
      const versionNo = isPlainObject(raw) ? positiveInteger(raw.version_no) : null
      const fileSize = isPlainObject(raw) ? raw.file_size : undefined
      const sha256 = isPlainObject(raw) ? raw.sha256 : undefined
      if (
        !isPlainObject(raw) ||
        versionNo === null ||
        typeof fileSize !== 'number' ||
        !Number.isSafeInteger(fileSize) ||
        fileSize < 0 ||
        typeof sha256 !== 'string' ||
        !SHA256_HEX.test(sha256)
      ) {
        dropped += 1
        continue
      }
      if (seen.has(versionNo)) {
        throw new OnlineAppearanceError('BAD_RESPONSE', '分享站返回的版本列表有重复版本号')
      }
      seen.add(versionNo)
      versions.push({
        versionNo,
        fileSize,
        sha256: sha256.toLowerCase(),
        changeNote: clipText(raw.change_note, 2000),
        createdAt: clipText(raw.created_at, 64),
      })
    }
    if (dropped > 0) logger.warn(`在线外观 ${fileKey} 有 ${dropped} 个版本信息不完整，已忽略`)
    return versions.sort((left, right) => right.versionNo - left.versionNo)
  }

  const fetchVersions = async (fileKey: string): Promise<OnlineAppearanceVersion[]> =>
    mapVersions(
      await requestJson(`${fileUrl(fileKey)}/versions`, '分享站上找不到这个外观包'),
      fileKey
    )

  const dropEntry = (token: string): void => {
    const entry = cache.get(token)
    if (!entry) return
    cache.delete(token)
    removeQuietly(entry.path)
  }

  const purgeExpired = (): void => {
    const current = now()
    for (const [token, entry] of cache) {
      if (!entry.installing && current - entry.createdAt > settings.cacheTtlMs) dropEntry(token)
    }
  }

  const registerEntry = (token: string, entry: CacheEntry): void => {
    cache.set(token, entry)
    for (const [oldest, oldEntry] of cache) {
      if (cache.size <= settings.cacheEntries) break
      if (oldest === token || oldEntry.installing) continue
      dropEntry(oldest)
    }
  }

  /**
   * 流式下载到 `<token>.part`，边下边算 SHA-256 与字节数；超过 16 MiB 或站端登记的大小
   * 就立即中止，任何失败都删掉 .part。
   */
  const download = async (
    fileKey: string,
    versionNo: number,
    expectedBytes: number,
    partPath: string
  ): Promise<{ bytes: number; sha256: string }> => {
    const limit = APPEARANCE_LIMITS.archiveBytes
    const controller = new AbortController()
    let timedOut = false
    let timer: NodeJS.Timeout | undefined
    const arm = (): void => {
      if (timer) clearTimeout(timer)
      timer = setTimeout(() => {
        timedOut = true
        controller.abort()
      }, settings.downloadIdleTimeoutMs)
    }
    let response: OnlineResponseLike | undefined
    let reader: BodyReader | undefined
    let handle: fs.promises.FileHandle | undefined
    arm()
    try {
      try {
        response = await fetchImpl(
          `${fileUrl(fileKey)}/download?version_no=${encodeURIComponent(String(versionNo))}`,
          { signal: controller.signal, headers: { Accept: 'application/octet-stream' } }
        )
      } catch {
        throw networkError(timedOut)
      }
      assertSecureResponse(response)
      if (response.status !== 200) throw statusError(response.status, '分享站上找不到这个版本')
      const declared = response.headers.get('content-length')
      if (declared !== null && /^\d+$/.test(declared.trim()) && Number(declared) > limit) {
        throw new OnlineAppearanceError('TOO_LARGE', '外观包超过 16 MiB 上限')
      }
      if (!response.body) throw new OnlineAppearanceError('BAD_RESPONSE', '分享站返回了空响应')
      reader = response.body.getReader()
      fs.mkdirSync(path.dirname(partPath), { recursive: true })
      handle = await fs.promises.open(partPath, 'wx')
      const hash = crypto.createHash('sha256')
      let bytes = 0
      for (;;) {
        let chunk: { done: boolean; value?: Uint8Array }
        try {
          chunk = await reader.read()
        } catch {
          throw networkError(timedOut, true)
        }
        if (chunk.done) break
        arm()
        if (!chunk.value || chunk.value.byteLength === 0) continue
        bytes += chunk.value.byteLength
        if (bytes > limit) throw new OnlineAppearanceError('TOO_LARGE', '外观包超过 16 MiB 上限')
        if (bytes > expectedBytes) {
          throw new OnlineAppearanceError(
            'CHECKSUM_MISMATCH',
            '下载内容比分享站登记的大小更大，已停止下载'
          )
        }
        hash.update(chunk.value)
        await handle.write(chunk.value)
      }
      await handle.close()
      handle = undefined
      return { bytes, sha256: hash.digest('hex') }
    } catch (error) {
      controller.abort()
      if (reader) void reader.cancel().catch(() => undefined)
      else cancelBody(response)
      if (handle) await handle.close().catch(() => undefined)
      removeQuietly(partPath)
      throw error
    } finally {
      if (timer) clearTimeout(timer)
    }
  }

  const list = async (query: OnlineAppearanceQuery): Promise<OnlineAppearanceListResult> => {
    if (!isPlainObject(query)) return invalidArgument('查询参数无效')
    const page = query.page === undefined ? 1 : positiveInteger(query.page)
    const pageSize = query.pageSize === undefined ? 20 : positiveInteger(query.pageSize)
    if (page === null) return invalidArgument('页码无效')
    if (pageSize === null || pageSize > 50) return invalidArgument('每页数量无效')
    if (query.keyword !== undefined && typeof query.keyword !== 'string') {
      return invalidArgument('搜索关键字无效')
    }
    const keyword = (query.keyword ?? '').trim()
    if (Array.from(keyword).length > 64 || hasControlChar(keyword)) {
      return invalidArgument('搜索关键字过长或包含不可用字符')
    }

    const url = new URL(`${baseUrl}/files`)
    url.searchParams.set('project_key', settings.projectKey)
    url.searchParams.set('category_key', settings.categoryKey)
    url.searchParams.set('page', String(page))
    url.searchParams.set('page_size', String(pageSize))
    if (keyword) url.searchParams.set('keyword', keyword)
    try {
      const data = await requestJson(url.toString(), '分享站上找不到外观分类')
      if (!isPlainObject(data) || !Array.isArray(data.items)) {
        throw new OnlineAppearanceError('BAD_RESPONSE', '分享站返回的列表格式不正确')
      }
      const sources = readAppearanceSources(options.userDataPath(), logger)
      const items = data.items
        .map(raw => mapItem(raw, sources))
        .filter((item): item is OnlineAppearanceItem => item !== null)
      const rawPagination = isPlainObject(data.pagination) ? data.pagination : {}
      const total = rawPagination.total
      return {
        success: true,
        items,
        pagination: {
          page: positiveInteger(rawPagination.page) ?? page,
          pageSize: positiveInteger(rawPagination.page_size) ?? pageSize,
          total:
            typeof total === 'number' && Number.isSafeInteger(total) && total >= 0
              ? total
              : items.length,
          hasNext: rawPagination.has_next === true,
        },
      }
    } catch (error) {
      logger.warn(`获取在线外观列表失败: ${errorMessage(error)}`)
      return failure(error, logger)
    }
  }

  const detail = async (fileKey: unknown): Promise<OnlineAppearanceDetailResult> => {
    if (!isValidOnlineFileKey(fileKey)) return invalidArgument('外观包标识无效')
    try {
      const [data, versions] = await Promise.all([
        requestJson(fileUrl(fileKey), '分享站上找不到这个外观包'),
        fetchVersions(fileKey),
      ])
      const item = mapItem(data, readAppearanceSources(options.userDataPath(), logger))
      if (!item || item.fileKey !== fileKey) {
        throw new OnlineAppearanceError('BAD_RESPONSE', '分享站返回的外观信息格式不正确')
      }
      return { success: true, item, versions }
    } catch (error) {
      logger.warn(`获取在线外观详情失败: ${fileKey}，${errorMessage(error)}`)
      return failure(error, logger)
    }
  }

  const prepare = async (
    fileKey: unknown,
    versionNo: unknown
  ): Promise<OnlineAppearancePrepareResult> => {
    if (!isValidOnlineFileKey(fileKey)) return invalidArgument('外观包标识无效')
    const pinnedVersion = positiveInteger(versionNo)
    if (pinnedVersion === null) return invalidArgument('版本号无效')
    purgeExpired()
    try {
      const versions = await fetchVersions(fileKey)
      const version = versions.find(item => item.versionNo === pinnedVersion)
      if (!version) {
        throw new OnlineAppearanceError('NOT_FOUND', '分享站上找不到这个版本')
      }
      if (version.fileSize > APPEARANCE_LIMITS.archiveBytes) {
        throw new OnlineAppearanceError('TOO_LARGE', '外观包超过 16 MiB 上限')
      }
      const cacheDir = options.cacheDir()
      const token = crypto.randomUUID()
      const partPath = path.join(cacheDir, `${token}.part`)
      const zipPath = path.join(cacheDir, `${token}.zip`)
      logger.info(
        `开始下载在线外观: ${fileKey} 版本 ${version.versionNo}，大小 ${version.fileSize} 字节`
      )
      const downloaded = await download(fileKey, version.versionNo, version.fileSize, partPath)
      if (downloaded.bytes !== version.fileSize || downloaded.sha256 !== version.sha256) {
        removeQuietly(partPath)
        logger.warn(
          `在线外观校验失败: ${fileKey} 版本 ${version.versionNo}，期望 ${version.fileSize} 字节 / ${version.sha256}，实际 ${downloaded.bytes} 字节 / ${downloaded.sha256}`
        )
        throw new OnlineAppearanceError('CHECKSUM_MISMATCH', '下载的外观包校验失败，请重试')
      }
      logger.info(
        `在线外观校验通过: ${fileKey} 版本 ${version.versionNo}，SHA-256 ${version.sha256}`
      )
      try {
        fs.renameSync(partPath, zipPath)
      } catch (error) {
        removeQuietly(partPath)
        throw error
      }

      let inspected: ReturnType<typeof inspectAppearancePackage>
      try {
        inspected = inspectAppearancePackage(zipPath)
      } catch (error) {
        removeQuietly(zipPath)
        if (error instanceof AppearanceError) {
          logger.warn(`在线外观包无效: ${fileKey} 版本 ${version.versionNo}，${error.message}`)
          return { success: false, code: 'INVALID_PACKAGE', error: error.message }
        }
        throw error
      }

      registerEntry(token, {
        path: zipPath,
        fileKey,
        versionNo: version.versionNo,
        sha256: version.sha256,
        fileSize: version.fileSize,
        createdAt: now(),
        installing: false,
      })
      const { manifest, previewUrl } = inspected
      const existing = getAppearance(options.userDataPath(), manifest.id)
      const tokens = Object.fromEntries(
        Object.entries(manifest.tokens).filter(([, value]) => value !== undefined)
      ) as AppearanceManifest['tokens']
      return {
        success: true,
        token,
        fileKey,
        versionNo: version.versionNo,
        fileSize: version.fileSize,
        sha256: version.sha256,
        appearance: {
          id: manifest.id,
          name: manifest.name,
          ...(manifest.description === undefined ? {} : { description: manifest.description }),
          mode: manifest.mode,
          tokens,
          ...(previewUrl ? { previewUrl } : {}),
        },
        existing: existing ? { id: existing.id, name: existing.name } : null,
      }
    } catch (error) {
      logger.warn(`准备在线外观失败: ${fileKey} 版本 ${pinnedVersion}，${errorMessage(error)}`)
      return failure(error, logger)
    }
  }

  /**
   * 安装已校验的临时包。全程同步执行，同一 token 的并发调用由事件循环串行化；
   * `installing` 标记额外挡住将来改成异步后的重入。
   */
  const install = (token: unknown, replace: boolean): OnlineAppearanceInstallResult => {
    purgeExpired()
    const entry = typeof token === 'string' ? cache.get(token) : undefined
    if (typeof token !== 'string' || !entry) {
      return { success: false, code: 'EXPIRED', error: '下载的外观包已过期，请重新下载' }
    }
    if (entry.installing) {
      return { success: false, code: 'IMPORT_FAILED', error: '这个外观包正在安装，请稍候' }
    }
    entry.installing = true
    try {
      let data: Buffer
      try {
        data = fs.readFileSync(entry.path)
      } catch {
        dropEntry(token)
        return { success: false, code: 'EXPIRED', error: '下载的外观包已过期，请重新下载' }
      }
      const actual = crypto.createHash('sha256').update(data).digest('hex')
      if (data.length !== entry.fileSize || actual !== entry.sha256) {
        dropEntry(token)
        logger.warn(`在线外观缓存文件被改动，已拒绝安装: ${entry.fileKey} 版本 ${entry.versionNo}`)
        return {
          success: false,
          code: 'CHECKSUM_MISMATCH',
          error: '下载的外观包校验失败，请重新下载',
        }
      }

      const userDataPath = options.userDataPath()
      const result = importAppearancePackage(userDataPath, entry.path, replace)
      if (result.success && result.appearance) {
        try {
          setAppearanceSource(
            userDataPath,
            result.appearance.id,
            {
              origin,
              projectKey: settings.projectKey,
              categoryKey: settings.categoryKey,
              fileKey: entry.fileKey,
              versionNo: entry.versionNo,
              sha256: entry.sha256,
              installedAt: new Date(now()).toISOString(),
            },
            logger
          )
        } catch (error) {
          logger.warn(`写入外观来源记录失败: ${errorMessage(error)}`)
        }
        dropEntry(token)
        logger.info(
          `在线外观已安装: ${result.appearance.id}（${entry.fileKey} 版本 ${entry.versionNo}${replace ? '，覆盖安装' : ''}）`
        )
        return result
      }
      if (result.code === 'DUPLICATE_ID' && !replace) {
        logger.info(
          `在线外观与本机外观 ID 相同，等待确认覆盖: ${entry.fileKey} 版本 ${entry.versionNo}`
        )
        return result
      }
      dropEntry(token)
      logger.warn(
        `在线外观安装失败: ${entry.fileKey} 版本 ${entry.versionNo}，${result.error ?? result.code ?? '未知错误'}`
      )
      return result
    } finally {
      entry.installing = false
    }
  }

  const discard = (token: unknown): { success: boolean } => {
    if (typeof token === 'string') dropEntry(token)
    return { success: true }
  }

  const clearCacheDirectory = (): void => {
    let cacheDir: string
    let names: string[]
    try {
      cacheDir = options.cacheDir()
      names = fs.readdirSync(cacheDir)
    } catch {
      return
    }
    const inUse = new Set([...cache.values()].map(entry => path.basename(entry.path)))
    for (const name of names) {
      if (!CACHE_FILE.test(name) || inUse.has(name)) continue
      const filePath = path.join(cacheDir, name)
      try {
        if (fs.lstatSync(filePath).isFile()) fs.rmSync(filePath, { force: true })
      } catch {
        // 被占用的旧文件留到下次启动再清。
      }
    }
  }

  return { list, detail, prepare, install, discard, clearCacheDirectory }
}

function stripUndefined<T extends object>(value: T): Partial<T> {
  return Object.fromEntries(
    Object.entries(value).filter(([, item]) => item !== undefined)
  ) as Partial<T>
}
