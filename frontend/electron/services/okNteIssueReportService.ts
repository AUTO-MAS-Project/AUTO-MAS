import * as fs from 'fs'
import * as path from 'path'
import AdmZip = require('adm-zip')

import { getLogger } from './logger'
import {
  CollectorState,
  addDebugDirectory,
  addDirectory,
  addLatestMasHistoryLog,
  addPerInstallationFile,
  discoverInstallations,
  resolveDataRoots,
} from './issueReportCore'

const logger = getLogger('OK-NTE问题包')

// 与 app/task/OkNte/AutoProxy.py 的 script_log_path 默认值保持同步
const OKNTE_REL_LOG_FILE = 'data/apps/ok-nte/working/logs/ok-script.log'

interface OkNteIssueReportResult {
  success: boolean
  message?: string
  zipPath?: string
  error?: string
}

export function createOkNteIssueReport(appRoot: string, zipPath: string): OkNteIssueReportResult {
  const zip = new AdmZip()
  const state: CollectorState = { zip, entries: [], archiveBytes: 0 }
  const dataRoots = resolveDataRoots(appRoot)
  const installations = discoverInstallations(dataRoots, {
    configType: 'OkNteConfig',
    pathField: 'RootPath',
    labelPrefix: 'oknte',
  })
  addLatestMasHistoryLog(state, dataRoots)

  dataRoots.forEach((dataRoot, index) => {
    addDebugDirectory(
      state,
      path.join(dataRoot, 'debug'),
      index === 0 ? 'logs/auto-mas' : 'logs/auto-mas/backend',
      'oknte'
    )
  })

  const runtimeDebugDir = path.join(path.dirname(process.execPath), 'debug')
  const knownDebugDirs = new Set(dataRoots.map(dataRoot => path.resolve(dataRoot, 'debug')))
  if (!knownDebugDirs.has(path.resolve(runtimeDebugDir))) {
    addDirectory(state, runtimeDebugDir, 'logs/frontend-runtime')
  }

  addPerInstallationFile(state, installations, OKNTE_REL_LOG_FILE, 'oknte')

  try {
    fs.mkdirSync(path.dirname(zipPath), { recursive: true })
    zip.writeZip(zipPath)
    logger.info(`OK-NTE 问题包已导出: ${zipPath}`)
    return {
      success: true,
      message: `OK-NTE 问题包导出成功，已收集 ${state.entries.filter(entry => entry.status !== 'skipped').length} 个文件`,
      zipPath,
    }
  } catch (error) {
    logger.error(`OK-NTE 问题包导出失败: ${String(error)}`)
    return {
      success: false,
      error: error instanceof Error ? error.message : String(error),
    }
  }
}
