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
  addLatestMasHistoryLog,
  addSanitizedJsonFile,
  discoverInstallations,
  resolveDataRoots,
} from './issueReportCore'

const logger = getLogger('Whimbox问题包')

// 与 app/task/Whimbox/tools/feed.py 的 LOG_FILE_PREFIX 保持同步
const WHIMBOX_LOG_PREFIX = 'whimbox-'

function addLatestWhimboxScriptLog(state: CollectorState, installations: Installation[]): void {
  let latest: { sourcePath: string; archivePath: string; mtimeMs: number } | undefined

  for (const installation of installations) {
    const logsDir = path.join(installation.rootPath, 'logs')
    let entries: fs.Dirent[]
    try {
      entries = fs.readdirSync(logsDir, { withFileTypes: true })
    } catch (error) {
      logger.debug(`读取奇想盒日志目录失败: ${logsDir}, ${String(error)}`)
      continue
    }

    for (const entry of entries) {
      if (!entry.isFile() || !entry.name.startsWith(WHIMBOX_LOG_PREFIX)) {
        continue
      }

      const logPath = path.join(logsDir, entry.name)
      try {
        const mtimeMs = fs.statSync(logPath).mtimeMs
        if (!latest || mtimeMs > latest.mtimeMs) {
          latest = {
            sourcePath: logPath,
            archivePath: `whimbox/${installation.label}/${entry.name}`,
            mtimeMs,
          }
        }
      } catch (error) {
        logger.debug(`读取奇想盒日志信息失败: ${logPath}, ${String(error)}`)
      }
    }
  }

  if (latest) {
    addDiagnosticFile(state, latest.sourcePath, latest.archivePath)
  }
}

function addLatestWhimboxConfigSnapshot(state: CollectorState, dataRoots: string[]): void {
  let latest: { sourcePath: string; mtimeMs: number } | undefined

  for (const dataRoot of dataRoots) {
    // 恢复池归档布局：data/WhimboxBackups/native/<指纹桶>/<时间戳>/config.json
    // （app/task/Whimbox/tools/upstream.py 的 backup_root）；指纹桶在主进程侧
    // 不可还原，取全局最新一份透传（仅通用脱敏，不做语义解读）
    const bucketsRoot = path.join(dataRoot, 'data', 'WhimboxBackups', 'native')
    let buckets: fs.Dirent[]
    try {
      buckets = fs.readdirSync(bucketsRoot, { withFileTypes: true })
    } catch (error) {
      logger.debug(`读取奇想盒恢复池失败: ${bucketsRoot}, ${String(error)}`)
      continue
    }

    for (const bucket of buckets) {
      if (!bucket.isDirectory()) {
        continue
      }

      const bucketDir = path.join(bucketsRoot, bucket.name)
      let times: fs.Dirent[]
      try {
        times = fs.readdirSync(bucketDir, { withFileTypes: true })
      } catch (error) {
        logger.debug(`读取奇想盒恢复池条目失败: ${bucketDir}, ${String(error)}`)
        continue
      }

      for (const time of times) {
        const snapshotPath = path.join(bucketDir, time.name, 'config.json')
        try {
          const mtimeMs = fs.statSync(snapshotPath).mtimeMs
          if (!latest || mtimeMs > latest.mtimeMs) {
            latest = { sourcePath: snapshotPath, mtimeMs }
          }
        } catch (error) {
          logger.debug(`读取奇想盒配置快照信息失败: ${snapshotPath}, ${String(error)}`)
        }
      }
    }
  }

  if (latest) {
    addSanitizedJsonFile(state, latest.sourcePath, 'whimbox/config-snapshot/config.json')
  }
}

interface WhimboxIssueReportResult {
  success: boolean
  message?: string
  zipPath?: string
  error?: string
}

export function createWhimboxIssueReport(
  appRoot: string,
  zipPath: string
): WhimboxIssueReportResult {
  const zip = new AdmZip()
  const state: CollectorState = { zip, entries: [], archiveBytes: 0 }
  const dataRoots = resolveDataRoots(appRoot)
  const installations = discoverInstallations(dataRoots, {
    configType: 'WhimboxConfig',
    pathField: 'RootPath',
    labelPrefix: 'whimbox',
  })
  addLatestMasHistoryLog(state, dataRoots)

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

  addLatestWhimboxScriptLog(state, installations)
  addLatestWhimboxConfigSnapshot(state, dataRoots)

  try {
    fs.mkdirSync(path.dirname(zipPath), { recursive: true })
    zip.writeZip(zipPath)
    logger.info(`Whimbox 问题包已导出: ${zipPath}`)
    return {
      success: true,
      message: `Whimbox 问题包导出成功，已收集 ${state.entries.filter(entry => entry.status !== 'skipped').length} 个文件`,
      zipPath,
    }
  } catch (error) {
    logger.error(`Whimbox 问题包导出失败: ${String(error)}`)
    return {
      success: false,
      error: error instanceof Error ? error.message : String(error),
    }
  }
}
