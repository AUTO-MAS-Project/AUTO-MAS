import * as fs from 'fs'
import * as path from 'path'
import AdmZip = require('adm-zip')

import { getLogger } from './logger'
import {
  CollectorState,
  Installation,
  addDebugDirectory,
  addDiagnosticFile,
  addDirectory,
  addRecentAdapterHistoryLogs,
  addSkippedEntry,
  discoverInstallations,
  resolveDataRoots,
} from './issueReportCore'

const logger = getLogger('HSR问题包')

/** 三月七按天滚动：logs/2026-11-13.log；取最近三天，覆盖跨午夜与前一天的失败 */
const M7A_LOG_PATTERN = /^\d{4}-\d{2}-\d{2}\.log$/
const M7A_LOG_DAYS = 3
/** SRA 日志在共享的 %APPDATA%/SRA/logs：sra20261113.log、同日续写 sra20261113_001.log */
const SRA_LOG_PATTERN = /^sra\d{8}(?:_\d+)?\.log$/
const SRA_LOG_COUNT = 5

interface HSRIssueReportResult {
  success: boolean
  incompleteCount?: number
  message?: string
  zipPath?: string
  error?: string
}

/** 目录里按名字排序（命名即日期序）取最后 count 个匹配文件；目录不存在返回 null */
function listRecentLogs(logDir: string, pattern: RegExp, count: number): string[] | null {
  try {
    return fs
      .readdirSync(logDir, { withFileTypes: true })
      .filter(entry => entry.isFile() && pattern.test(entry.name))
      .map(entry => entry.name)
      .sort()
      .slice(-count)
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === 'ENOENT') return null
    throw error
  }
}

function addRecentLogs(
  state: CollectorState,
  logDir: string,
  archiveDir: string,
  pattern: RegExp,
  count: number
): void {
  let files: string[] | null
  try {
    files = listRecentLogs(logDir, pattern, count)
  } catch (error) {
    // 目录不存在属正常（从没跑过）；权限等其余失败记跳过，免得日志静默丢失
    logger.debug(`读取 HSR 日志目录失败: ${logDir}, ${String(error)}`)
    addSkippedEntry(state, archiveDir, 0, '无法读取日志目录')
    return
  }
  for (const name of files ?? []) {
    addDiagnosticFile(state, path.join(logDir, name), path.posix.join(archiveDir, name), {
      text: true,
    })
  }
}

function resolveSraAppData(): string | undefined {
  const appData = process.env.APPDATA
  return appData ? path.join(appData, 'SRA') : undefined
}

export function createHSRIssueReport(appRoot: string, zipPath: string): HSRIssueReportResult {
  const zip = new AdmZip()
  const state: CollectorState = { zip, entries: [], archiveBytes: 0 }
  const dataRoots = resolveDataRoots(appRoot)

  const m7aInstallations: Installation[] = discoverInstallations(dataRoots, {
    configType: 'HSRConfig',
    pathField: 'M7APath',
    labelPrefix: 'm7a',
  })
  const sraInstallations: Installation[] = discoverInstallations(dataRoots, {
    configType: 'HSRConfig',
    pathField: 'SRAPath',
    labelPrefix: 'sra',
  })

  // 最近三次失败的 MAS 运行记录；一次没失败过就带最近一次
  addRecentAdapterHistoryLogs(state, dataRoots, {
    adapter: 'hsr',
    fallbackLatest: true,
    includeJson: true,
  })

  // HSR 不往 debug/ 下落专项子目录，只收顶层通用日志
  dataRoots.forEach((dataRoot, index) => {
    addDebugDirectory(
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

  for (const installation of m7aInstallations) {
    addRecentLogs(
      state,
      path.join(installation.rootPath, 'logs'),
      path.posix.join('hsr', installation.label, 'logs'),
      M7A_LOG_PATTERN,
      M7A_LOG_DAYS
    )
  }

  // SRA 的日志不在安装目录里，所有 SRA 安装共用一份 appdata；配过 SRA 才收
  const sraAppData = sraInstallations.length ? resolveSraAppData() : undefined
  if (sraAppData) {
    addRecentLogs(
      state,
      path.join(sraAppData, 'logs'),
      'hsr/sra-appdata/logs',
      SRA_LOG_PATTERN,
      SRA_LOG_COUNT
    )
  }

  try {
    fs.mkdirSync(path.dirname(zipPath), { recursive: true })
    zip.writeZip(zipPath)
    logger.info(`HSR 问题包已导出: ${zipPath}`)
    return {
      success: true,
      incompleteCount: state.entries.filter(entry => entry.status !== 'included').length,
      message: `HSR 问题包导出成功，已收集 ${state.entries.filter(entry => entry.status !== 'skipped').length} 个文件`,
      zipPath,
    }
  } catch (error) {
    logger.error(`HSR 问题包导出失败: ${String(error)}`)
    return {
      success: false,
      error: error instanceof Error ? error.message : String(error),
    }
  }
}
