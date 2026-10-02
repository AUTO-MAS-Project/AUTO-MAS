import * as fs from 'fs'
import * as path from 'path'
import { deflateRawSync } from 'zlib'
import AdmZip = require('adm-zip')

import { getLogger } from './logger'
import {
  CollectorState,
  addDebugDirectory,
  addDirectory,
  addRecentFailedMaaEndHistoryLogs,
  discoverInstallations,
  isRecord,
  resolveDataRoots,
} from './issueReportCore'

const logger = getLogger('MaaEnd问题包')

// 对齐 MXU src-tauri/src/commands/file_ops.rs 的 export_logs。
const MAX_VOLUME_BYTES = 24_500_000
const IMAGE_EXTENSIONS = new Set(['.png', '.jpg', '.jpeg'])
const DEBUG_EXTENSIONS = new Set(['.log', '.json', '.dmp'])
const TEXT_EXTENSIONS = new Set(['.log', '.json', '.txt', '.toml', '.yaml', '.yml', '.xml', '.csv'])

interface MxuExportEntry {
  sourcePath: string
  archiveName: string
}

function sortEntries(entries: MxuExportEntry[]): MxuExportEntry[] {
  return entries.sort((a, b) =>
    a.archiveName < b.archiveName ? -1 : a.archiveName > b.archiveName ? 1 : 0
  )
}

function collectFiles(dir: string, prefix: string): MxuExportEntry[] {
  if (!fs.existsSync(dir) || !fs.statSync(dir).isDirectory()) return []
  const files: MxuExportEntry[] = []
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const sourcePath = path.join(dir, entry.name)
    const archiveName = path.posix.join(prefix, entry.name)
    if (entry.isDirectory()) files.push(...collectFiles(sourcePath, archiveName))
    else if (entry.isFile()) files.push({ sourcePath, archiveName })
  }
  return sortEntries(files)
}

function collectImages(debugDir: string, subdir: string): MxuExportEntry[] {
  const dir = path.join(debugDir, subdir)
  if (!fs.existsSync(dir) || !fs.statSync(dir).isDirectory()) return []
  return fs
    .readdirSync(dir, { withFileTypes: true })
    .filter(entry => entry.isFile() && IMAGE_EXTENSIONS.has(path.extname(entry.name).toLowerCase()))
    .map(entry => ({
      sourcePath: path.join(dir, entry.name),
      archiveName: `${subdir}/${entry.name}`,
    }))
    .sort((a, b) => fs.statSync(b.sourcePath).mtimeMs - fs.statSync(a.sourcePath).mtimeMs)
}

function collectMxuEntries(rootPath: string): MxuExportEntry[] {
  const debugDir = path.join(rootPath, 'debug')
  if (!fs.existsSync(debugDir)) throw new Error(`日志目录不存在: ${debugDir}`)
  const debugEntries = fs.readdirSync(debugDir, { withFileTypes: true })
  const rootLogs = sortEntries(
    debugEntries
      .filter(
        entry => entry.isFile() && ['.log', '.dmp'].includes(path.extname(entry.name).toLowerCase())
      )
      .map(entry => ({ sourcePath: path.join(debugDir, entry.name), archiveName: entry.name }))
  )
  const subdirLogs = sortEntries(
    debugEntries
      .filter(entry => entry.isDirectory())
      .flatMap(entry => collectFiles(path.join(debugDir, entry.name), entry.name))
      .filter(entry => DEBUG_EXTENSIONS.has(path.extname(entry.sourcePath).toLowerCase()))
  )
  return [
    ...rootLogs,
    ...collectFiles(path.join(rootPath, 'config'), 'config'),
    ...subdirLogs,
    ...collectImages(debugDir, 'on_error'),
    ...collectImages(debugDir, 'vision'),
  ]
}

interface MxuProject {
  projectName: string
  projectVersion: string
}

async function loadMxuProject(apiEndpoint: string, scriptId: string): Promise<MxuProject> {
  const response = await fetch(`${apiEndpoint}/api/scripts/maaend/options`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ scriptId }),
    signal: AbortSignal.timeout(30_000),
  })
  if (!response.ok) throw new Error(`读取 MaaEnd 资源失败: HTTP ${response.status}`)
  const data: unknown = await response.json()
  if (!isRecord(data) || data.code !== 200) {
    throw new Error(
      isRecord(data) && typeof data.message === 'string' ? data.message : '读取 MaaEnd 资源失败'
    )
  }
  if (typeof data.projectName !== 'string' || typeof data.projectVersion !== 'string') {
    throw new Error('MaaEnd 资源未返回项目名称和版本，请更新后端')
  }
  return { projectName: data.projectName, projectVersion: data.projectVersion }
}

function mxuExportName(project: MxuProject, now: Date): string {
  const { projectName: name, projectVersion: version } = project
  const pad = (value: number) => String(value).padStart(2, '0')
  const stamp = `${now.getFullYear()}${pad(now.getMonth() + 1)}${pad(now.getDate())}-${pad(now.getHours())}${pad(now.getMinutes())}${pad(now.getSeconds())}`
  return version ? `${name}-logs-${version}-${stamp}` : `${name}-logs-${stamp}`
}

function addMxuVolumes(
  state: CollectorState,
  rootPath: string,
  label: string,
  project: MxuProject,
  now: Date
): void {
  const entries = collectMxuEntries(rootPath)
  if (!entries.length) throw new Error(`没有可导出的日志文件: ${rootPath}`)
  const name = mxuExportName(project, now)
  const width = entries.length >= 100 ? 3 : 2
  let volume = new AdmZip(undefined, { noSort: true })
  let writtenBytes = 0
  let centralDirectoryBytes = 22 // ZIP EOCD
  let volumeIndex = 1
  let fileCount = 0

  const flush = () => {
    const content = volume.toBuffer()
    const archivePath = `maaend/${label}/${name}/${name}-part${String(volumeIndex).padStart(width, '0')}.zip`
    // 用户要求 MaaEnd 部分完整沿用 MXU：原样分卷，不套 MAS 的脱敏、截断和总量上限。
    state.zip.addFile(archivePath, content)
    state.entries.push({
      path: archivePath,
      sourceSize: content.length,
      storedSize: content.length,
      status: 'included',
    })
    volumeIndex += 1
    volume = new AdmZip(undefined, { noSort: true })
    writtenBytes = 0
    centralDirectoryBytes = 22
    fileCount = 0
  }

  for (const entry of entries) {
    let content: Buffer
    try {
      content = fs.readFileSync(entry.sourcePath)
    } catch (error) {
      logger.warn(`无法打开文件 ${entry.sourcePath}: ${String(error)}`)
      continue
    }
    // 与 MXU 一样按压缩后大小切卷；单个超大文件独占一卷，不能截断或丢弃。
    const compressedBytes = deflateRawSync(content).length
    const nameBytes = Buffer.byteLength(entry.archiveName)
    const directoryBytes = 46 + nameBytes
    const currentBytes = writtenBytes + centralDirectoryBytes
    const estimatedBytes = TEXT_EXTENSIONS.has(path.extname(entry.sourcePath).toLowerCase())
      ? Math.floor(content.length / 4)
      : content.length
    // 沿用 MXU 的两阶段容量判断：估算触线后再用 DEFLATE 实际大小判定。
    if (
      fileCount &&
      currentBytes + estimatedBytes + 64 + directoryBytes > MAX_VOLUME_BYTES &&
      currentBytes + compressedBytes + 64 + directoryBytes > MAX_VOLUME_BYTES
    )
      flush()
    volume.addFile(entry.archiveName, content)
    // MXU CountingWriter 也计入 CRC/大小字段回写的 12 字节。
    writtenBytes += compressedBytes + 30 + nameBytes + 12
    centralDirectoryBytes += directoryBytes
    fileCount += 1
  }
  if (fileCount) flush()
}

interface MaaEndIssueReportResult {
  success: boolean
  message?: string
  zipPath?: string
  error?: string
}

export async function createMaaEndIssueReport(
  appRoot: string,
  zipPath: string,
  apiEndpoint: string
): Promise<MaaEndIssueReportResult> {
  const zip = new AdmZip()
  const state: CollectorState = { zip, entries: [], archiveBytes: 0 }
  const dataRoots = resolveDataRoots(appRoot)
  const installations = discoverInstallations(dataRoots, {
    configType: 'MaaEndConfig',
    pathField: 'Path',
    labelPrefix: 'maaend',
  })
  addRecentFailedMaaEndHistoryLogs(state, dataRoots)

  dataRoots.forEach((dataRoot, index) => {
    addDebugDirectory(
      state,
      path.join(dataRoot, 'debug'),
      index === 0 ? 'logs/auto-mas' : 'logs/auto-mas/backend',
      'maaend'
    )
  })

  const runtimeDebugDir = path.join(path.dirname(process.execPath), 'debug')
  const knownDebugDirs = new Set(dataRoots.map(dataRoot => path.resolve(dataRoot, 'debug')))
  if (!knownDebugDirs.has(path.resolve(runtimeDebugDir))) {
    addDirectory(state, runtimeDebugDir, 'logs/frontend-runtime')
  }

  try {
    const now = new Date()
    for (const installation of installations) {
      const project = await loadMxuProject(apiEndpoint, installation.scriptId)
      addMxuVolumes(state, installation.rootPath, installation.label, project, now)
    }
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
