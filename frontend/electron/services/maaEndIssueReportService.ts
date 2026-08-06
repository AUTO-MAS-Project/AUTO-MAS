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
  version?: string
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

function readVersionFromInterface(rootPath: string): string | undefined {
  const interfacePath = path.join(rootPath, 'interface.json')
  if (!fs.existsSync(interfacePath)) {
    return undefined
  }

  const data = readJson(interfacePath)
  if (isRecord(data) && typeof data.version === 'string') {
    return data.version
  }

  try {
    const text = fs.readFileSync(interfacePath, 'utf-8')
    return text.match(/"version"\s*:\s*"([^"]+)"/)?.[1]
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
        version: readVersionFromInterface(normalizedPath),
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

function readAutoMasVersion(dataRoots: string[]): string | undefined {
  for (const dataRoot of dataRoots) {
    const versionData = readJson(path.join(dataRoot, 'res', 'version.json'))
    if (isRecord(versionData) && typeof versionData.version === 'string') {
      return versionData.version
    }
  }
  return undefined
}

function buildIssueTemplate(archiveName: string, autoMasVersion?: string): string {
  return `# MaaEnd Issue 信息

## 问题描述及复现步骤

预期行为：

实际行为：

复现步骤：
1. 
2. 
3. 

## 日志文件

已生成：\`${archiveName}\`。
压缩包中的 \`logs/\`、\`maaend/\` 和 \`metadata/\` 目录由 AUTO-MAS 自动收集。
请将这个 ZIP 原文件发送到 AUTO-MAS 官方 QQ 群（群号：957750551），不要解压或修改。

## 软件画面截图

请将出现问题时完整的 MaaEnd 软件画面截图一并发送到 MAS 群。

## 游戏画面截图

请将出现问题时的游戏画面截图一并发送到 MAS 群。

## 版本信息截图

请将 MaaEnd「设置 - 调试 - 版本信息」截图一并发送到 MAS 群。
压缩包中的 \`metadata/collection-manifest.json\` 同时记录了可复制粘贴的版本信息。

## 其他信息

- AUTO-MAS 版本：${autoMasVersion || '未知'}
- 请确认提交前已经更新到最新版本的 MaaEnd。
`
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
  const generatedAt = new Date().toISOString()
  const dataRoots = resolveDataRoots(appRoot)
  const installations = discoverMaaEndInstallations(dataRoots)
  const autoMasVersion = readAutoMasVersion(dataRoots)
  const installationManifest: Array<Record<string, unknown>> = []

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
    const debugIncluded = addDirectory(
      state,
      path.join(installation.rootPath, 'debug'),
      `maaend/${installation.label}/debug`
    )
    const onErrorIncluded = addDirectory(
      state,
      path.join(installation.rootPath, 'on_error'),
      `maaend/${installation.label}/on_error`
    )
    const configIncluded = addSanitizedJsonFile(
      state,
      path.join(installation.rootPath, 'config', 'mxu-MaaEnd.json'),
      `maaend/${installation.label}/config/mxu-MaaEnd.json`
    )

    installationManifest.push({
      id: installation.label,
      version: installation.version || '未知',
      debugIncluded,
      onErrorIncluded,
      configIncluded,
    })
  }

  const metadata = {
    formatVersion: 1,
    generatedAt,
    autoMasVersion: autoMasVersion || '未知',
    system: {
      platform: process.platform,
      platformRelease: os.release(),
      architecture: process.arch,
      nodeVersion: process.version,
    },
    maaend: installationManifest,
    notes: [
      '配置中的路径、账号密码、Token、Cookie、Secret 等字段会脱敏；日志文本会按常见键值格式脱敏并隐藏当前用户目录。',
      '单个文件最大保留 25 MiB，问题包总大小最大保留 95 MiB。超限文本文件仅保留末尾内容。',
      '当前流程请先将问题包原文件发送到 AUTO-MAS 官方 QQ 群；软件截图、游戏截图和版本信息截图可在群内补充。',
    ],
    entries: state.entries,
  }

  state.zip.addFile(
    'metadata/system-info.json',
    Buffer.from(`${JSON.stringify(metadata.system, null, 2)}\n`, 'utf-8')
  )
  state.zip.addFile(
    'issue-template.md',
    Buffer.from(buildIssueTemplate(path.basename(zipPath), autoMasVersion), 'utf-8')
  )
  state.zip.addFile(
    'metadata/collection-manifest.json',
    Buffer.from(`${JSON.stringify(metadata, null, 2)}\n`, 'utf-8')
  )

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
