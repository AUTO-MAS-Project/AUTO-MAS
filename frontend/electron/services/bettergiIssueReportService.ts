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
  discoverInstallations,
  resolveDataRoots,
} from './issueReportCore'

const logger = getLogger('BetterGI问题包')

// 与 app/task/BetterGI/AutoProxy.py 的 _BGI_REL_LOG_DIR / _BGI_LOG_FILE_PREFIX 保持同步；
// BetterGI 的 Serilog 日志按天滚动（better-genshin-impact{yyyyMMdd}.log），没有固定文件名
const BGI_REL_LOG_DIR = 'log'
const BGI_LOG_FILE_PREFIX = 'better-genshin-impact'

function addLatestBetterGILog(state: CollectorState, installations: Installation[]): void {
  let latest: { sourcePath: string; archivePath: string; mtimeMs: number } | undefined

  for (const installation of installations) {
    const logDir = path.join(installation.rootPath, ...BGI_REL_LOG_DIR.split('/'))
    let entries: fs.Dirent[]
    try {
      entries = fs.readdirSync(logDir, { withFileTypes: true })
    } catch (error) {
      logger.debug(`读取 BetterGI 日志目录失败: ${logDir}, ${String(error)}`)
      continue
    }

    for (const entry of entries) {
      if (
        !entry.isFile() ||
        !entry.name.startsWith(BGI_LOG_FILE_PREFIX) ||
        !entry.name.toLowerCase().endsWith('.log')
      ) {
        continue
      }

      const logPath = path.join(logDir, entry.name)
      try {
        const mtimeMs = fs.statSync(logPath).mtimeMs
        if (!latest || mtimeMs > latest.mtimeMs) {
          latest = {
            sourcePath: logPath,
            archivePath: `bettergi/${installation.label}/log/${entry.name}`,
            mtimeMs,
          }
        }
      } catch (error) {
        logger.debug(`读取 BetterGI 日志信息失败: ${logPath}, ${String(error)}`)
      }
    }
  }

  if (latest) {
    addDiagnosticFile(state, latest.sourcePath, latest.archivePath)
  }
}

interface BetterGIIssueReportResult {
  success: boolean
  message?: string
  zipPath?: string
  error?: string
}

export function createBetterGIIssueReport(
  appRoot: string,
  zipPath: string
): BetterGIIssueReportResult {
  const zip = new AdmZip()
  const state: CollectorState = { zip, entries: [], archiveBytes: 0 }
  const dataRoots = resolveDataRoots(appRoot)
  const installations = discoverInstallations(dataRoots, {
    configType: 'BetterGIConfig',
    pathField: 'RootPath',
    labelPrefix: 'bettergi',
  })
  addLatestMasHistoryLog(state, dataRoots)

  // 后端 debug 目录含 MAS 切号的 OCR 诊断（debug/bgi-account-switch/ 的
  // switch-detail-*.log 与错误截图），是定位切号/OCR 问题的关键材料；
  // 其他专项（okww/oknte/maaend）的诊断子目录不收
  dataRoots.forEach((dataRoot, index) => {
    addDebugDirectory(
      state,
      path.join(dataRoot, 'debug'),
      index === 0 ? 'logs/auto-mas' : 'logs/auto-mas/backend',
      'bettergi'
    )
  })

  const runtimeDebugDir = path.join(path.dirname(process.execPath), 'debug')
  const knownDebugDirs = new Set(dataRoots.map(dataRoot => path.resolve(dataRoot, 'debug')))
  if (!knownDebugDirs.has(path.resolve(runtimeDebugDir))) {
    addDirectory(state, runtimeDebugDir, 'logs/frontend-runtime')
  }

  addLatestBetterGILog(state, installations)

  try {
    fs.mkdirSync(path.dirname(zipPath), { recursive: true })
    zip.writeZip(zipPath)
    logger.info(`BetterGI 问题包已导出: ${zipPath}`)
    return {
      success: true,
      message: `BetterGI 问题包导出成功，已收集 ${state.entries.filter(entry => entry.status !== 'skipped').length} 个文件`,
      zipPath,
    }
  } catch (error) {
    logger.error(`BetterGI 问题包导出失败: ${String(error)}`)
    return {
      success: false,
      error: error instanceof Error ? error.message : String(error),
    }
  }
}
