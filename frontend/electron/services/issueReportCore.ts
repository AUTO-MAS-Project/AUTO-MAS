import * as fs from 'fs'
import * as os from 'os'
import * as path from 'path'
import AdmZip = require('adm-zip')

import { getLogger } from './logger'

const logger = getLogger('问题包')

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

export interface ReportEntry {
  path: string
  sourceSize: number
  storedSize: number
}

export interface CollectorState {
  zip: AdmZip
  entries: ReportEntry[]
}

export interface HistoryLogCandidate {
  sourcePath: string
  archivePath: string
  mtimeMs: number
}

export function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

export function isTextFile(filePath: string): boolean {
  return TEXT_EXTENSIONS.has(path.extname(filePath).toLowerCase())
}

export function sanitizeText(text: string): string {
  let sanitized = text.replace(SENSITIVE_BEARER_PATTERN, '$1***')
  sanitized = sanitized.replace(SENSITIVE_ASSIGNMENT_PATTERN, '$1***')
  const homePath = os.homedir()
  if (homePath) {
    sanitized = sanitized.split(homePath).join('<HOME>')
  }
  return sanitized
}

export function sanitizeJsonValue(value: unknown): unknown {
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

export interface InstallationOptions {
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

export function addEntry(
  state: CollectorState,
  archivePath: string,
  sourceSize: number,
  content: Buffer
): void {
  state.zip.addFile(archivePath, content)
  state.entries.push({
    path: archivePath,
    sourceSize,
    storedSize: content.byteLength,
  })
}

export function readDiagnosticContent(filePath: string): Buffer {
  const rawText = fs.readFileSync(filePath, 'utf-8')
  if (path.extname(filePath).toLowerCase() === '.json') {
    const json = readJson(filePath)
    if (json !== undefined) {
      return Buffer.from(`${JSON.stringify(sanitizeJsonValue(json), null, 2)}\n`, 'utf-8')
    }
  }
  return Buffer.from(sanitizeText(rawText), 'utf-8')
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

  if (isTextFile(sourcePath)) {
    try {
      const content = readDiagnosticContent(sourcePath)
      addEntry(state, archivePath, stat.size, content)
      return
    } catch (error) {
      logger.debug(`读取文本文件失败: ${sourcePath}, ${String(error)}`)
      return
    }
  }

  try {
    addEntry(state, archivePath, stat.size, fs.readFileSync(sourcePath))
  } catch (error) {
    logger.debug(`读取二进制文件失败: ${sourcePath}, ${String(error)}`)
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
      const content = Buffer.from(`${JSON.stringify(sanitizeJsonValue(json), null, 2)}\n`, 'utf-8')
      const sourceSize = fs.statSync(sourcePath).size
      addEntry(state, archivePath, sourceSize, content)
    }
    return true
  } catch (error) {
    logger.debug(`脱敏配置失败: ${sourcePath}, ${String(error)}`)
    return false
  }
}

export function addLatestMasHistoryLog(
  state: CollectorState,
  dataRoots: string[]
): string | undefined {
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
