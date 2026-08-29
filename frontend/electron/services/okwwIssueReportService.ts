import * as fs from 'fs'
import * as path from 'path'
import AdmZip = require('adm-zip')

import { getLogger } from './logger'
import {
  CollectorState,
  addDiagnosticFile,
  addDirectory,
  addLatestMasHistoryLog,
  isRecord,
  readJson,
  resolveDataRoots,
} from './issueReportCore'

const logger = getLogger('OK-WW问题包')

// 与 app/task/Okww/AutoProxy.py 的 _OKWW_REL_LOG_FILE 保持同步
const OKWW_REL_LOG_FILE = 'data/apps/ok-ww/working/logs/ok-script.log'

interface OkwwInstallation {
  label: string
  rootPath: string
}

interface ScriptConfigRecord {
  instances?: Array<{ uid?: string; type?: string }>
  [key: string]: unknown
}

function discoverOkwwInstallations(dataRoots: string[]): OkwwInstallation[] {
  const installations: OkwwInstallation[] = []
  const seenPaths = new Set<string>()

  for (const dataRoot of dataRoots) {
    const config = readJson(path.join(dataRoot, 'config', 'ScriptConfig.json'))
    if (!isRecord(config)) {
      continue
    }

    const records = config as ScriptConfigRecord
    for (const instance of records.instances || []) {
      if (instance?.type !== 'Okww' || !instance.uid) {
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
        label: `okww-${installations.length + 1}`,
        rootPath: normalizedPath,
      })
    }
  }

  return installations
}

function addLatestOkwwScriptLog(
  state: CollectorState,
  installations: OkwwInstallation[]
): void {
  let latest: { sourcePath: string; archivePath: string; mtimeMs: number } | undefined

  for (const installation of installations) {
    const logPath = path.join(installation.rootPath, ...OKWW_REL_LOG_FILE.split('/'))
    try {
      const mtimeMs = fs.statSync(logPath).mtimeMs
      if (!latest || mtimeMs > latest.mtimeMs) {
        latest = {
          sourcePath: logPath,
          archivePath: `okww/${installation.label}/ok-script.log`,
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

export interface OkwwIssueReportResult {
  success: boolean
  message?: string
  zipPath?: string
  error?: string
}

export function createOkwwIssueReport(appRoot: string, zipPath: string): OkwwIssueReportResult {
  const zip = new AdmZip()
  const state: CollectorState = { zip, entries: [], archiveBytes: 0 }
  const dataRoots = resolveDataRoots(appRoot)
  const installations = discoverOkwwInstallations(dataRoots)
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

  addLatestOkwwScriptLog(state, installations)

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
