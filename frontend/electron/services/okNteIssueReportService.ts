import * as fs from 'fs'
import * as path from 'path'
import AdmZip = require('adm-zip')

import { getLogger } from './logger'
import {
  CollectorState,
  Installation,
  addDiagnosticFile,
  addDirectory,
  addLatestMasHistoryLog,
  discoverInstallations,
  resolveDataRoots,
} from './issueReportCore'

const logger = getLogger('OK-NTE问题包')

// 与 app/task/OkNte/AutoProxy.py 的 script_log_path 默认值保持同步
const OKNTE_REL_LOG_FILE = 'data/apps/ok-nte/working/logs/ok-script.log'

function addLatestOkNteScriptLog(
  state: CollectorState,
  installations: Installation[]
): void {
  let latest: { sourcePath: string; archivePath: string; mtimeMs: number } | undefined

  for (const installation of installations) {
    const logPath = path.join(installation.rootPath, ...OKNTE_REL_LOG_FILE.split('/'))
    try {
      const mtimeMs = fs.statSync(logPath).mtimeMs
      if (!latest || mtimeMs > latest.mtimeMs) {
        latest = {
          sourcePath: logPath,
          archivePath: `oknte/${installation.label}/ok-script.log`,
          mtimeMs,
        }
      }
    } catch (error) {
      logger.debug(`读取 ok-script.log 失败: ${logPath}, ${String(error)}`)
    }
  }

  if (latest) {
    addDiagnosticFile(state, latest.sourcePath, latest.archivePath)
  }
}

export interface OkNteIssueReportResult {
  success: boolean
  message?: string
  zipPath?: string
  error?: string
}

export function createOkNteIssueReport(appRoot: string, zipPath: string): OkNteIssueReportResult {
  const zip = new AdmZip()
  const state: CollectorState = { zip, entries: [] }
  const dataRoots = resolveDataRoots(appRoot)
  const installations = discoverInstallations(dataRoots, {
    configType: 'OkNteConfig',
    pathField: 'RootPath',
    labelPrefix: 'oknte',
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

  addLatestOkNteScriptLog(state, installations)

  try {
    fs.mkdirSync(path.dirname(zipPath), { recursive: true })
    zip.writeZip(zipPath)
    logger.info(`OK-NTE 问题包已导出: ${zipPath}`)
    return {
      success: true,
      message: `OK-NTE 问题包导出成功，已收集 ${state.entries.length} 个文件`,
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
