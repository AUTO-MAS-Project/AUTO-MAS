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

const logger = getLogger('OK-WW问题包')

// 与 app/task/Okww/AutoProxy.py 的 _OKWW_REL_LOG_FILE 保持同步
const OKWW_REL_LOG_FILE = 'data/apps/ok-ww/working/logs/ok-script.log'

interface OkwwIssueReportResult {
  success: boolean
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

  try {
    fs.mkdirSync(path.dirname(zipPath), { recursive: true })
    zip.writeZip(zipPath)
    logger.info(`OK-WW 问题包已导出: ${zipPath}`)
    return {
      success: true,
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
