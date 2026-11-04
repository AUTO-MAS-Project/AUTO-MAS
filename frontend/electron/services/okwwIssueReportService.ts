import * as fs from 'fs'
import * as path from 'path'
import AdmZip = require('adm-zip')

import { getLogger } from './logger'
import {
  CollectorState,
  addDebugDirectory,
  addDiagnosticFile,
  addDirectory,
  addLatestMasHistoryLog,
  addPerInstallationFile,
  addSkippedEntry,
  discoverInstallations,
  resolveDataRoots,
} from './issueReportCore'

const logger = getLogger('OK-WW问题包')

// 与 app/task/Okww/AutoProxy.py 的 _OKWW_REL_LOG_FILE 保持同步
const OKWW_REL_LOG_FILE = 'data/apps/ok-ww/working/logs/ok-script.log'

interface OkwwIssueReportResult {
  success: boolean
  incompleteCount?: number
  message?: string
  zipPath?: string
  error?: string
}

export function createOkwwIssueReport(appRoot: string, zipPath: string): OkwwIssueReportResult {
  const zip = new AdmZip()
  const state: CollectorState = { zip, entries: [], archiveBytes: 0 }
  const dataRoots = resolveDataRoots(appRoot)
  const installations = discoverInstallations(dataRoots, {
    configType: 'OkwwConfig',
    pathField: 'RootPath',
    labelPrefix: 'okww',
  })
  addLatestMasHistoryLog(state, dataRoots)

  dataRoots.forEach((dataRoot, index) => {
    addDebugDirectory(
      state,
      path.join(dataRoot, 'debug'),
      index === 0 ? 'logs/auto-mas' : 'logs/auto-mas/backend',
      'okww'
    )
  })

  const runtimeDebugDir = path.join(path.dirname(process.execPath), 'debug')
  const knownDebugDirs = new Set(dataRoots.map(dataRoot => path.resolve(dataRoot, 'debug')))
  if (!knownDebugDirs.has(path.resolve(runtimeDebugDir))) {
    addDirectory(state, runtimeDebugDir, 'logs/frontend-runtime')
  }

  addPerInstallationFile(state, installations, OKWW_REL_LOG_FILE, 'okww')
  // 启动器更新发生在工作日志创建之前，每个安装单独收集启动器日志；
  // 按天滚动的命名排序即日期序，取最近两天以覆盖跨午夜的自更新排查。
  for (const installation of installations) {
    const logDir = path.join(installation.rootPath, 'logs')
    let files: string[]
    try {
      files = fs
        .readdirSync(logDir, { withFileTypes: true })
        .filter(entry => entry.isFile() && /^app\.\d{4}-\d{2}-\d{2}$/.test(entry.name))
        .map(entry => entry.name)
        .sort()
        .slice(-2)
    } catch (error) {
      // 目录不存在属正常状态（启动器尚未运行过）；无权限等其余读取失败
      // 记跳过条目，避免启动器日志静默丢失。
      if ((error as NodeJS.ErrnoException).code === 'ENOENT') continue
      logger.debug(`读取 OK-WW 启动器日志失败: ${logDir}, ${String(error)}`)
      addSkippedEntry(
        state,
        path.posix.join('okww', installation.label, 'launcher'),
        0,
        '无法读取启动器日志目录'
      )
      continue
    }
    for (const name of files) {
      addDiagnosticFile(
        state,
        path.join(logDir, name),
        path.posix.join('okww', installation.label, 'launcher', name)
      )
    }
  }

  try {
    fs.mkdirSync(path.dirname(zipPath), { recursive: true })
    zip.writeZip(zipPath)
    logger.info(`OK-WW 问题包已导出: ${zipPath}`)
    return {
      success: true,
      incompleteCount: state.entries.filter(entry => entry.status !== 'included').length,
      message: `OK-WW 问题包导出成功，已收集 ${state.entries.filter(entry => entry.status !== 'skipped').length} 个文件`,
      zipPath,
    }
  } catch (error) {
    logger.error(`OK-WW 问题包导出失败: ${String(error)}`)
    return {
      success: false,
      error: error instanceof Error ? error.message : String(error),
    }
  }
}
