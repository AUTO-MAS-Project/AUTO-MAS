import * as fs from 'fs'
import * as path from 'path'
import AdmZip = require('adm-zip')

import { getLogger } from './logger'
import {
  CollectorState,
  addDirectory,
  addLatestMasHistoryLog,
  addSanitizedJsonFile,
  discoverInstallations,
  resolveDataRoots,
} from './issueReportCore'

const logger = getLogger('MaaEnd问题包')

export interface MaaEndIssueReportResult {
  success: boolean
  message?: string
  zipPath?: string
  error?: string
}

export function createMaaEndIssueReport(appRoot: string, zipPath: string): MaaEndIssueReportResult {
  const zip = new AdmZip()
  const state: CollectorState = { zip, entries: [] }
  const dataRoots = resolveDataRoots(appRoot)
  const installations = discoverInstallations(dataRoots, {
    configType: 'MaaEndConfig',
    pathField: 'Path',
    labelPrefix: 'maaend',
  })
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
      message: `MaaEnd 问题包导出成功，已收集 ${state.entries.length} 个文件`,
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
