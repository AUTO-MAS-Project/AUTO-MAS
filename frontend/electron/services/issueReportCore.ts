import * as fs from 'fs'
import * as os from 'os'
import * as path from 'path'
import AdmZip = require('adm-zip')

import { getLogger } from './logger'

const logger = getLogger('问题包')

const MAX_ENTRY_BYTES = 25 * 1024 * 1024
const MAX_ARCHIVE_BYTES = 95 * 1024 * 1024
const TEXT_EXTENSIONS = new Set([
  '.cfg',
  '.csv',
  '.ini',
  '.json',
  '.jsonc',
  '.log',
  '.md',
  '.out',
  '.txt',
  '.xml',
  '.yaml',
  '.yml',
])
const SENSITIVE_KEY_PATTERN =
  /(?:password|passwd|token|cookie|secret|authorization|credential|api[_-]?key|stoken|ltoken|serverchan|path)/i
const SENSITIVE_BEARER_PATTERN =
  /((?:["']?[\w-]*(?:password|passwd|token|cookie|secret|authorization|credential|api[_-]?key|stoken|ltoken|serverchan|path)[\w-]*["']?\s*[:=]\s*["']?(?:Bearer|Basic)\s+))[^"'\s,;&}\]]+/gi
const SENSITIVE_ASSIGNMENT_PATTERN =
  /((?:["']?[\w-]*(?:password|passwd|token|cookie|secret|authorization|credential|api[_-]?key|stoken|ltoken|serverchan|path)[\w-]*["']?\s*[:=]\s*["']?))(?!Bearer\b|Basic\b)[^"'\s,;&}\]]+/gi
// 上面两条正则在大文件上每 MB 各要十几毫秒；第一条命中的必要条件是出现「: Bearer 」这种形状，
// 先用便宜得多的这条筛一遍
const BEARER_OR_BASIC_PATTERN = /[:=]\s*["']?(?:Bearer|Basic)\s/i

interface ReportEntry {
  path: string
  sourceSize: number
  storedSize: number
  status: 'included' | 'truncated' | 'skipped'
  reason?: string
}

export interface CollectorState {
  zip: AdmZip
  entries: ReportEntry[]
  archiveBytes: number
  /** 单个文件、整包的原始字节上限，不填按 25 MB / 95 MB */
  maxEntryBytes?: number
  maxArchiveBytes?: number
}

function entryLimit(state: CollectorState): number {
  return state.maxEntryBytes ?? MAX_ENTRY_BYTES
}

function archiveLimit(state: CollectorState): number {
  return state.maxArchiveBytes ?? MAX_ARCHIVE_BYTES
}

interface HistoryLogCandidate {
  sourcePath: string
  archivePath: string
  mtimeMs: number
}

interface HistoryRecordCandidate {
  logPath: string
  jsonPath: string
  archiveRoot: string
  relativeBasePath: string
  mtimeMs: number
}

function historyArchiveRoot(rootIndex: number): string {
  return rootIndex === 0 ? 'logs/mas-history' : 'logs/mas-history/backend'
}

export function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function isTextFile(filePath: string): boolean {
  return TEXT_EXTENSIONS.has(path.extname(filePath).toLowerCase())
}

function sanitizeText(text: string): string {
  let sanitized = BEARER_OR_BASIC_PATTERN.test(text)
    ? text.replace(SENSITIVE_BEARER_PATTERN, '$1***')
    : text
  sanitized = sanitized.replace(SENSITIVE_ASSIGNMENT_PATTERN, '$1***')
  const homePath = os.homedir()
  if (homePath) {
    sanitized = sanitized.split(homePath).join('<HOME>')
  }
  return sanitized
}

function sanitizeJsonValue(value: unknown): unknown {
  if (Array.isArray(value)) {
    return value.map(item => sanitizeJsonValue(item))
  }

  if (typeof value === 'string') {
    return sanitizeText(value)
  }

  if (!isRecord(value)) {
    return value
  }

  return Object.fromEntries(
    Object.entries(value).map(([key, item]) => [
      key,
      SENSITIVE_KEY_PATTERN.test(key) ? '***' : sanitizeJsonValue(item),
    ])
  )
}

export function readJson(filePath: string): unknown {
  try {
    return JSON.parse(fs.readFileSync(filePath, 'utf-8').replace(/^\uFEFF/, ''))
  } catch {
    return undefined
  }
}

export function resolveDataRoots(appRoot: string): string[] {
  const roots = [path.resolve(appRoot)]
  const parentRoot = path.resolve(appRoot, '..')
  if (
    parentRoot !== roots[0] &&
    (fs.existsSync(path.join(parentRoot, 'main.py')) || fs.existsSync(path.join(parentRoot, 'app')))
  ) {
    roots.push(parentRoot)
  }
  return roots
}

interface InstallationOptions {
  /** ScriptConfig.json 实例记录中的类型值，如 'OkwwConfig' / 'MaaEndConfig' */
  configType: string
  /** 安装目录字段名，如 'RootPath' / 'Path' */
  pathField: 'Path' | 'RootPath'
  /** 问题包归档目录的标签前缀，如 'okww' */
  labelPrefix: string
}

export interface Installation {
  label: string
  rootPath: string
}

interface ScriptConfigRecord {
  instances?: Array<{ uid?: string; type?: string }>
  [key: string]: unknown
}

export function discoverInstallations(
  dataRoots: string[],
  options: InstallationOptions
): Installation[] {
  const installations: Installation[] = []
  const seenPaths = new Set<string>()

  for (const dataRoot of dataRoots) {
    const config = readJson(path.join(dataRoot, 'config', 'ScriptConfig.json'))
    if (!isRecord(config)) {
      continue
    }

    const records = config as ScriptConfigRecord
    for (const instance of records.instances || []) {
      if (instance?.type !== options.configType || !instance.uid) {
        continue
      }

      const scriptConfig = records[instance.uid]
      const info =
        isRecord(scriptConfig) && isRecord(scriptConfig.Info) ? scriptConfig.Info : undefined
      const rootPath =
        info && typeof info[options.pathField] === 'string'
          ? (info[options.pathField] as string).trim()
          : ''
      if (!rootPath) {
        continue
      }

      const normalizedPath = path.resolve(rootPath)
      const pathKey = process.platform === 'win32' ? normalizedPath.toLowerCase() : normalizedPath
      if (seenPaths.has(pathKey)) {
        continue
      }

      seenPaths.add(pathKey)
      installations.push({
        label: `${options.labelPrefix}-${installations.length + 1}`,
        rootPath: normalizedPath,
      })
    }
  }

  return installations
}

function addEntry(
  state: CollectorState,
  archivePath: string,
  sourceSize: number,
  content: Buffer,
  status: ReportEntry['status'],
  reason?: string
): void {
  state.zip.addFile(archivePath, content)
  state.archiveBytes += content.byteLength
  state.entries.push({
    path: archivePath,
    sourceSize,
    storedSize: content.byteLength,
    status,
    reason,
  })
}

function addSkippedEntry(
  state: CollectorState,
  archivePath: string,
  sourceSize: number,
  reason: string
): void {
  state.entries.push({
    path: archivePath,
    sourceSize,
    storedSize: 0,
    status: 'skipped',
    reason,
  })
}

function readDiagnosticContent(filePath: string): Buffer {
  const rawText = fs.readFileSync(filePath, 'utf-8')
  if (path.extname(filePath).toLowerCase() === '.json') {
    const json = readJson(filePath)
    if (json !== undefined) {
      return Buffer.from(`${JSON.stringify(sanitizeJsonValue(json), null, 2)}\n`, 'utf-8')
    }
  }
  return Buffer.from(sanitizeText(rawText), 'utf-8')
}

// 截出来的末尾从第一个完整行开始：半行的开头可能是被截断的键名，脱敏认不出来，值就原样漏出去
// （还可能截出半个 UTF-8 字符）。窗口里连一个换行都没有就什么也不留
function fromFirstFullLine(chunk: Buffer): Buffer {
  const newline = chunk.indexOf(0x0a)
  return newline >= 0 ? chunk.subarray(newline + 1) : Buffer.alloc(0)
}

/** 读文件末尾最多 bytes 字节。 */
function readTextTail(filePath: string, bytes: number): Buffer {
  const fd = fs.openSync(filePath, 'r')
  try {
    const size = fs.fstatSync(fd).size
    const start = Math.max(0, size - bytes)
    const buffer = Buffer.alloc(size - start)
    const chunk = buffer.subarray(0, fs.readSync(fd, buffer, 0, buffer.length, start))
    return start > 0 ? fromFirstFullLine(chunk) : chunk
  } finally {
    fs.closeSync(fd)
  }
}

/** 已脱敏的内容取末尾最多 bytes 字节。 */
function tailOf(content: Buffer, bytes: number): Buffer {
  return content.byteLength <= bytes
    ? content
    : fromFirstFullLine(content.subarray(content.byteLength - bytes))
}

export function addDiagnosticFile(
  state: CollectorState,
  sourcePath: string,
  archivePath: string
): void {
  let stat: fs.Stats
  try {
    stat = fs.statSync(sourcePath)
  } catch (error) {
    logger.debug(`读取诊断文件失败: ${sourcePath}, ${String(error)}`)
    return
  }

  if (!stat.isFile()) {
    return
  }

  const maxEntryBytes = entryLimit(state)
  const remainingBytes = archiveLimit(state) - state.archiveBytes
  if (remainingBytes <= 0) {
    addSkippedEntry(state, archivePath, stat.size, '问题包已达到总大小限制')
    return
  }

  if (isTextFile(sourcePath)) {
    const storedSize = Math.min(maxEntryBytes, remainingBytes)
    const header = Buffer.from('[文件过大，仅保留文件末尾内容。]\n', 'utf-8')
    const keptBytes = storedSize - header.byteLength
    try {
      // 放不下的非 JSON 文本只读要保留的末尾那段再脱敏：几十 MB 的原生日志整份脱敏要好几秒
      const oversized = stat.size > storedSize && path.extname(sourcePath).toLowerCase() !== '.json'
      const sanitized = oversized ? undefined : readDiagnosticContent(sourcePath)
      if (sanitized && sanitized.byteLength <= storedSize) {
        addEntry(state, archivePath, stat.size, sanitized, 'included')
        return
      }
      if (keptBytes <= 0) {
        addSkippedEntry(state, archivePath, stat.size, '问题包已达到总大小限制')
        return
      }

      // 脱敏可能让内容变长，脱敏之后再按上限裁一次
      const tail = tailOf(
        sanitized ??
          Buffer.from(sanitizeText(readTextTail(sourcePath, keptBytes).toString('utf-8')), 'utf-8'),
        keptBytes
      )
      if (tail.byteLength === 0) {
        addSkippedEntry(state, archivePath, stat.size, '文件末尾一行就超过剩余空间')
        return
      }
      addEntry(
        state,
        `${archivePath}.tail`,
        stat.size,
        Buffer.concat([header, tail]),
        'truncated',
        storedSize < maxEntryBytes
          ? '问题包剩余空间不足，仅保留文件末尾'
          : `原始文件超过 ${maxEntryBytes} 字节`
      )
      return
    } catch (error) {
      addSkippedEntry(state, archivePath, stat.size, `读取文本文件失败: ${String(error)}`)
      return
    }
  }

  if (stat.size > maxEntryBytes || stat.size > remainingBytes) {
    addSkippedEntry(state, archivePath, stat.size, '二进制文件超过问题包大小限制')
    return
  }

  try {
    addEntry(state, archivePath, stat.size, fs.readFileSync(sourcePath), 'included')
  } catch (error) {
    addSkippedEntry(state, archivePath, stat.size, `读取二进制文件失败: ${String(error)}`)
  }
}

export function addDirectory(
  state: CollectorState,
  sourceDir: string,
  archiveDir: string
): boolean {
  if (!fs.existsSync(sourceDir)) {
    return false
  }

  let foundFile = false
  let entries: fs.Dirent[]
  try {
    entries = fs
      .readdirSync(sourceDir, { withFileTypes: true })
      .sort((left, right) => left.name.localeCompare(right.name))
  } catch (error) {
    logger.debug(`读取诊断目录失败: ${sourceDir}, ${String(error)}`)
    return false
  }

  for (const entry of entries) {
    if (entry.isSymbolicLink()) {
      continue
    }

    const sourcePath = path.join(sourceDir, entry.name)
    const archivePath = path.posix.join(archiveDir, entry.name)
    if (entry.isDirectory()) {
      foundFile = addDirectory(state, sourcePath, archivePath) || foundFile
    } else if (entry.isFile()) {
      addDiagnosticFile(state, sourcePath, archivePath)
      foundFile = true
    }
  }

  return foundFile
}

export function addSanitizedJsonFile(
  state: CollectorState,
  sourcePath: string,
  archivePath: string
): boolean {
  if (!fs.existsSync(sourcePath)) {
    return false
  }

  try {
    const json = readJson(sourcePath)
    if (json === undefined) {
      addDiagnosticFile(state, sourcePath, archivePath)
    } else {
      addSanitizedJsonValue(state, json, archivePath, fs.statSync(sourcePath).size)
    }
    return true
  } catch (error) {
    logger.debug(`脱敏配置失败: ${sourcePath}, ${String(error)}`)
    return false
  }
}

/** 把内存里的一段配置脱敏后写进问题包（例如从 ScriptConfig.json 里摘出的单个脚本）。 */
export function addSanitizedJsonValue(
  state: CollectorState,
  value: unknown,
  archivePath: string,
  sourceSize?: number
): void {
  const content = Buffer.from(`${JSON.stringify(sanitizeJsonValue(value), null, 2)}\n`, 'utf-8')
  const remainingBytes = archiveLimit(state) - state.archiveBytes
  if (content.byteLength > entryLimit(state) || content.byteLength > remainingBytes) {
    addSkippedEntry(
      state,
      archivePath,
      sourceSize ?? content.byteLength,
      '脱敏配置超过问题包大小限制'
    )
  } else {
    addEntry(state, archivePath, sourceSize ?? content.byteLength, content, 'included')
  }
}

/**
 * 最后写入的清单：收了哪些文件、哪些因大小限制被截断或跳过。
 * 清单本身很小，不计入总大小限制，保证包里总有它。
 */
export function addReportManifest(
  state: CollectorState,
  archivePath: string,
  details: Record<string, unknown>
): void {
  const manifest = { ...details, entries: state.entries }
  state.zip.addFile(archivePath, Buffer.from(`${JSON.stringify(manifest, null, 2)}\n`, 'utf-8'))
}

export function addLatestMasHistoryLog(
  state: CollectorState,
  dataRoots: string[]
): string | undefined {
  let latest: HistoryLogCandidate | undefined

  const visitDirectory = (historyRoot: string, currentDir: string, archiveRoot: string): void => {
    let entries: fs.Dirent[]
    try {
      entries = fs.readdirSync(currentDir, { withFileTypes: true })
    } catch (error) {
      logger.debug(`读取 MAS 历史日志目录失败: ${currentDir}, ${String(error)}`)
      return
    }

    for (const entry of entries) {
      if (entry.isSymbolicLink()) {
        continue
      }

      const sourcePath = path.join(currentDir, entry.name)
      if (entry.isDirectory()) {
        visitDirectory(historyRoot, sourcePath, archiveRoot)
        continue
      }

      if (!entry.isFile() || path.extname(entry.name).toLowerCase() !== '.log') {
        continue
      }

      try {
        const mtimeMs = fs.statSync(sourcePath).mtimeMs
        const relativePath = path.relative(historyRoot, sourcePath).replace(/\\/g, '/')
        const candidate = {
          sourcePath,
          archivePath: path.posix.join(archiveRoot, relativePath),
          mtimeMs,
        }
        if (
          !latest ||
          candidate.mtimeMs > latest.mtimeMs ||
          (candidate.mtimeMs === latest.mtimeMs && candidate.archivePath > latest.archivePath)
        ) {
          latest = candidate
        }
      } catch (error) {
        logger.debug(`读取 MAS 历史日志信息失败: ${sourcePath}, ${String(error)}`)
      }
    }
  }

  for (const [rootIndex, dataRoot] of dataRoots.entries()) {
    const historyRoot = path.join(dataRoot, 'history')
    if (fs.existsSync(historyRoot)) {
      visitDirectory(historyRoot, historyRoot, historyArchiveRoot(rootIndex))
    }
  }

  if (!latest) {
    return undefined
  }

  const entryCount = state.entries.length
  addDiagnosticFile(state, latest.sourcePath, latest.archivePath)
  if (state.entries.length === entryCount) {
    return undefined
  }
  return state.entries[state.entries.length - 1]?.path
}

export function addRecentFailedMaaEndHistoryLogs(
  state: CollectorState,
  dataRoots: string[],
  limit = 3
): string[] {
  const candidates: HistoryRecordCandidate[] = []
  const seenPaths = new Set<string>()

  const visitDirectory = (historyRoot: string, currentDir: string, archiveRoot: string): void => {
    let entries: fs.Dirent[]
    try {
      entries = fs.readdirSync(currentDir, { withFileTypes: true })
    } catch (error) {
      logger.debug(`读取 MaaEnd 历史日志目录失败: ${currentDir}, ${String(error)}`)
      return
    }

    for (const entry of entries) {
      if (entry.isSymbolicLink()) {
        continue
      }

      const sourcePath = path.join(currentDir, entry.name)
      if (entry.isDirectory()) {
        visitDirectory(historyRoot, sourcePath, archiveRoot)
        continue
      }

      if (!entry.isFile() || path.extname(entry.name).toLowerCase() !== '.json') {
        continue
      }

      const data = readJson(sourcePath)
      if (!isRecord(data) || typeof data.maaend_result !== 'string') {
        continue
      }

      const result = data.maaend_result.replace(/^\[[^\]]+\]\s*/, '')
      if (result === 'Success!') {
        continue
      }

      const normalizedPath = path.resolve(sourcePath)
      const pathKey = process.platform === 'win32' ? normalizedPath.toLowerCase() : normalizedPath
      if (seenPaths.has(pathKey)) {
        continue
      }

      try {
        const relativePath = path.relative(historyRoot, sourcePath).replace(/\\/g, '/')
        candidates.push({
          logPath: sourcePath.slice(0, -path.extname(sourcePath).length) + '.log',
          jsonPath: sourcePath,
          archiveRoot,
          relativeBasePath: relativePath.slice(0, -path.extname(relativePath).length),
          mtimeMs: fs.statSync(sourcePath).mtimeMs,
        })
        seenPaths.add(pathKey)
      } catch (error) {
        logger.debug(`读取 MaaEnd 历史日志信息失败: ${sourcePath}, ${String(error)}`)
      }
    }
  }

  for (const [rootIndex, dataRoot] of dataRoots.entries()) {
    const historyRoot = path.join(dataRoot, 'history')
    if (fs.existsSync(historyRoot)) {
      visitDirectory(historyRoot, historyRoot, historyArchiveRoot(rootIndex))
    }
  }

  const addedPaths: string[] = []
  const selected = candidates
    .sort(
      (left, right) =>
        right.mtimeMs - left.mtimeMs || right.relativeBasePath.localeCompare(left.relativeBasePath)
    )
    .slice(0, Math.max(limit, 0))

  for (const candidate of selected) {
    for (const [sourcePath, extension] of [
      [candidate.logPath, '.log'],
      [candidate.jsonPath, '.json'],
    ] as const) {
      const archivePath = path.posix.join(
        candidate.archiveRoot,
        `${candidate.relativeBasePath}${extension}`
      )
      const entryCount = state.entries.length
      addDiagnosticFile(state, sourcePath, archivePath)
      if (state.entries.length > entryCount) {
        addedPaths.push(state.entries[state.entries.length - 1].path)
      }
    }
  }

  return addedPaths
}
