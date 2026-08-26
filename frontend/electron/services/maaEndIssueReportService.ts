import * as fs from 'fs'
import * as os from 'os'
import * as path from 'path'
import AdmZip = require('adm-zip')

import { getLogger } from './logger'

const logger = getLogger('MaaEnd问题包')

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

interface MaaEndInstallation {
  label: string
  rootPath: string
}

interface ReportEntry {
  path: string
  sourceSize: number
  storedSize: number
  status: 'included' | 'truncated' | 'skipped'
  reason?: string
}

interface CollectorState {
  zip: AdmZip
  entries: ReportEntry[]
  archiveBytes: number
}

interface MaaEndConfigRecord {
  instances?: Array<{ uid?: string; type?: string }>
  [key: string]: unknown
}

interface HistoryLogCandidate {
  sourcePath: string
  archivePath: string
  mtimeMs: number
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function isTextFile(filePath: string): boolean {
  return TEXT_EXTENSIONS.has(path.extname(filePath).toLowerCase())
}

function sanitizeText(text: string): string {
  let sanitized = text.replace(SENSITIVE_BEARER_PATTERN, '$1***')
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

function readJson(filePath: string): unknown {
  try {
    return JSON.parse(fs.readFileSync(filePath, 'utf-8').replace(/^\uFEFF/, ''))
  } catch {
    return undefined
  }
}

function resolveDataRoots(appRoot: string): string[] {
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

function discoverMaaEndInstallations(dataRoots: string[]): MaaEndInstallation[] {
  const installations: MaaEndInstallation[] = []
  const seenPaths = new Set<string>()

  for (const dataRoot of dataRoots) {
    const config = readJson(path.join(dataRoot, 'config', 'ScriptConfig.json'))
    if (!isRecord(config)) {
      continue
    }

    const records = config as MaaEndConfigRecord
    for (const instance of records.instances || []) {
      if (instance?.type !== 'MaaEndConfig' || !instance.uid) {
        continue
      }

      const scriptConfig = records[instance.uid]
      const info =
        isRecord(scriptConfig) && isRecord(scriptConfig.Info) ? scriptConfig.Info : undefined
      const rootPath = info && typeof info.Path === 'string' ? info.Path.trim() : ''
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
        label: `maaend-${installations.length + 1}`,
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

function addDiagnosticFile(state: CollectorState, sourcePath: string, archivePath: string): void {
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

  const remainingBytes = MAX_ARCHIVE_BYTES - state.archiveBytes
  if (remainingBytes <= 0) {
    addSkippedEntry(state, archivePath, stat.size, '问题包已达到总大小限制')
    return
  }

  if (isTextFile(sourcePath)) {
    try {
      const content = readDiagnosticContent(sourcePath)
      if (content.byteLength <= MAX_ENTRY_BYTES && content.byteLength <= remainingBytes) {
        addEntry(state, archivePath, stat.size, content, 'included')
        return
      }

      const storedSize = Math.min(MAX_ENTRY_BYTES, remainingBytes)
      if (storedSize <= 0) {
        addSkippedEntry(state, archivePath, stat.size, '问题包已达到总大小限制')
        return
      }

      const tail = content.subarray(content.byteLength - storedSize)
      addEntry(
        state,
        `${archivePath}.tail`,
        stat.size,
        Buffer.concat([Buffer.from('[文件过大，仅保留文件末尾内容。]\n', 'utf-8'), tail]).subarray(
          0,
          storedSize
        ),
        'truncated',
        `原始文件超过 ${MAX_ENTRY_BYTES} 字节`
      )
      return
    } catch (error) {
      addSkippedEntry(state, archivePath, stat.size, `读取文本文件失败: ${String(error)}`)
      return
    }
  }

  if (stat.size > MAX_ENTRY_BYTES || stat.size > remainingBytes) {
    addSkippedEntry(state, archivePath, stat.size, '二进制文件超过问题包大小限制')
    return
  }

  try {
    addEntry(state, archivePath, stat.size, fs.readFileSync(sourcePath), 'included')
  } catch (error) {
    addSkippedEntry(state, archivePath, stat.size, `读取二进制文件失败: ${String(error)}`)
  }
}

function addDirectory(state: CollectorState, sourceDir: string, archiveDir: string): boolean {
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

function addSanitizedJsonFile(
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
      const content = Buffer.from(`${JSON.stringify(sanitizeJsonValue(json), null, 2)}\n`, 'utf-8')
      const sourceSize = fs.statSync(sourcePath).size
      const remainingBytes = MAX_ARCHIVE_BYTES - state.archiveBytes
      if (content.byteLength > MAX_ENTRY_BYTES || content.byteLength > remainingBytes) {
        addSkippedEntry(state, archivePath, sourceSize, '脱敏配置超过问题包大小限制')
      } else {
        addEntry(state, archivePath, sourceSize, content, 'included')
      }
    }
    return true
  } catch (error) {
    logger.debug(`脱敏配置失败: ${sourcePath}, ${String(error)}`)
    return false
  }
}

function addLatestMasHistoryLog(state: CollectorState, dataRoots: string[]): string | undefined {
  let latest: HistoryLogCandidate | undefined

  const visitDirectory = (historyRoot: string, currentDir: string): void => {
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
        visitDirectory(historyRoot, sourcePath)
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
          archivePath: path.posix.join('logs/mas-history', relativePath),
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

  for (const dataRoot of dataRoots) {
    const historyRoot = path.join(dataRoot, 'history')
    if (fs.existsSync(historyRoot)) {
      visitDirectory(historyRoot, historyRoot)
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

export interface MaaEndIssueReportResult {
  success: boolean
  message?: string
  zipPath?: string
  error?: string
}

export function createMaaEndIssueReport(appRoot: string, zipPath: string): MaaEndIssueReportResult {
  const zip = new AdmZip()
  const state: CollectorState = { zip, entries: [], archiveBytes: 0 }
  const dataRoots = resolveDataRoots(appRoot)
  const installations = discoverMaaEndInstallations(dataRoots)
  addLatestMasHistoryLog(state, dataRoots)

  dataRoots.forEach((dataRoot, index) => {
    addDirectory(
      state,
      path.join(dataRoot, 'debug'),
      index === 0 ? 'logs/auto-mas' : 'logs/auto-mas/backend'
    )
  })

  const runtimeDebugDir = path.join(path.dirname(process.execPath), 'debug')
  const knownDebugDirs = new Set(dataRoots.map(dataRoot => path.resolve(dataRoot, 'debug')))
  if (!knownDebugDirs.has(path.resolve(runtimeDebugDir))) {
    addDirectory(state, runtimeDebugDir, 'logs/frontend-runtime')
  }

  for (const installation of installations) {
    addDirectory(
      state,
      path.join(installation.rootPath, 'debug'),
      `maaend/${installation.label}/debug`
    )
    addDirectory(
      state,
      path.join(installation.rootPath, 'on_error'),
      `maaend/${installation.label}/on_error`
    )
    addSanitizedJsonFile(
      state,
      path.join(installation.rootPath, 'config', 'mxu-MaaEnd.json'),
      `maaend/${installation.label}/config/mxu-MaaEnd.json`
    )
  }

  try {
    fs.mkdirSync(path.dirname(zipPath), { recursive: true })
    zip.writeZip(zipPath)
    logger.info(`MaaEnd 问题包已导出: ${zipPath}`)
    return {
      success: true,
      message: `MaaEnd 问题包导出成功，已收集 ${state.entries.filter(entry => entry.status !== 'skipped').length} 个文件`,
      zipPath,
    }
  } catch (error) {
    logger.error(`MaaEnd 问题包导出失败: ${String(error)}`)
    return {
      success: false,
      error: error instanceof Error ? error.message : String(error),
    }
  }
}
