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
  addSanitizedJsonFile,
  discoverInstallations,
  resolveDataRoots,
} from './issueReportCore'

const logger = getLogger('ZZZ-OD问题包')

// 与 app/task/ZzzOd/AutoProxy.py 的 _ZZZOD_REL_LOG 保持同步
const ZZZOD_REL_LOG_FILE = '.log/log.txt'

function addLatestZzzOdScriptLog(
  state: CollectorState,
  installations: Installation[]
): void {
  let latest: { sourcePath: string; archivePath: string; mtimeMs: number } | undefined

  for (const installation of installations) {
    const logPath = path.join(installation.rootPath, ...ZZZOD_REL_LOG_FILE.split('/'))
    try {
      const mtimeMs = fs.statSync(logPath).mtimeMs
      if (!latest || mtimeMs > latest.mtimeMs) {
        latest = {
          sourcePath: logPath,
          archivePath: `zzzod/${installation.label}/log.txt`,
          mtimeMs,
        }
      }
    } catch (error) {
      logger.debug(`读取 log.txt 失败: ${logPath}, ${String(error)}`)
    }
  }

  if (latest) {
    addDiagnosticFile(state, latest.sourcePath, latest.archivePath)
  }
}

function addZzzOdConfigs(
  state: CollectorState,
  installations: Installation[]
): void {
  for (const installation of installations) {
    // 一条龙注册表（含 instance_list、instance_run 等全局设置）
    const registryPath = path.join(installation.rootPath, 'config', 'one_dragon.yml')
    addSanitizedJsonFile(state, registryPath, `zzzod/${installation.label}/config/one_dragon.yml`)
  }
}

interface ZzzOdIssueReportResult {
  success: boolean
  message?: string
  zipPath?: string
  error?: string
}

export function createZzzOdIssueReport(appRoot: string, zipPath: string): ZzzOdIssueReportResult {
  const zip = new AdmZip()
  const state: CollectorState = { zip, entries: [], archiveBytes: 0 }
  const dataRoots = resolveDataRoots(appRoot)
  const installations = discoverInstallations(dataRoots, {
    configType: 'ZzzOdConfig',
    pathField: 'RootPath',
    labelPrefix: 'zzzod',
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

  addLatestZzzOdScriptLog(state, installations)
  addZzzOdConfigs(state, installations)

  try {
    fs.mkdirSync(path.dirname(zipPath), { recursive: true })
    zip.writeZip(zipPath)
    logger.info(`ZZZ-OD 问题包已导出: ${zipPath}`)
    return {
      success: true,
      message: `ZZZ-OD 问题包导出成功，已收集 ${state.entries.filter(entry => entry.status !== 'skipped').length} 个文件`,
      zipPath,
    }
  } catch (error) {
    logger.error(`ZZZ-OD 问题包导出失败: ${String(error)}`)
    return {
      success: false,
      error: error instanceof Error ? error.message : String(error),
    }
  }
}
