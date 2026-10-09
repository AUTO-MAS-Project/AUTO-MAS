import * as fs from 'fs'
import * as path from 'path'
import AdmZip = require('adm-zip')

import { getLogger } from './logger'
import {
  CollectorState,
  addDebugDirectory,
  addDiagnosticFile,
  addDirectory,
  addRecentAdapterHistoryLogs,
  discoverInstallations,
  resolveDataRoots,
} from './issueReportCore'

const logger = getLogger('MAA问题包')
const PRIMARY_LOGS = ['gui.log', 'asst.log', 'gui.bak.log', 'asst.bak.log']
const IMAGE_EXTENSIONS = new Set(['.png', '.jpg', '.jpeg', '.bmp', '.webp'])
const isImage = (filePath: string): boolean =>
  IMAGE_EXTENSIONS.has(path.extname(filePath).toLowerCase())
const isLogOrImage = (filePath: string): boolean =>
  /\.log(?:\.zip)?$/i.test(filePath) || isImage(filePath)

export interface MaaIssueReportResult {
  success: boolean
  message?: string
  zipPath?: string
  error?: string
  /** 有文件缺失、被截断或未能收录时大于 0，界面按警告样式提示 */
  incompleteCount?: number
}

/** 逐个收录大文件时让主进程处理窗口事件。 */
const yieldToEventLoop = () => new Promise<void>(resolve => setImmediate(resolve))

/** 只收 interface 的图片，新现场优先，逐张读取时让主进程处理窗口事件。 */
async function addInterfaceImages(
  state: CollectorState,
  sourceDir: string,
  archiveDir: string
): Promise<void> {
  const files: Array<{ sourcePath: string; archivePath: string; mtimeMs: number }> = []
  addDirectory(state, sourceDir, archiveDir, {
    includeFile: isImage,
    addFile: (_, sourcePath, archivePath) => {
      try {
        files.push({ sourcePath, archivePath, mtimeMs: fs.statSync(sourcePath).mtimeMs })
      } catch {
        logger.debug(`截图已消失或无法读取: ${sourcePath}`)
      }
    },
  })
  files.sort((a, b) => b.mtimeMs - a.mtimeMs || a.archivePath.localeCompare(b.archivePath))
  for (const file of files) {
    addDiagnosticFile(state, file.sourcePath, file.archivePath)
    await yieldToEventLoop()
  }
}

export async function createMaaIssueReport(
  appRoot: string,
  zipPath: string
): Promise<MaaIssueReportResult> {
  const state: CollectorState = { zip: new AdmZip(), entries: [], archiveBytes: 0 }
  try {
    const dataRoots = resolveDataRoots(appRoot)
    const installations = discoverInstallations(dataRoots, {
      configType: 'MaaConfig',
      pathField: 'Path',
      labelPrefix: 'maa',
    })
    if (!installations.length)
      return { success: false, error: '未找到已配置安装路径的 MAA 脚本，请检查脚本设置' }

    // 每个安装的核心日志优先，各安装依次收同类文件。
    for (const name of PRIMARY_LOGS) {
      for (const installation of installations) {
        addDiagnosticFile(
          state,
          path.join(installation.rootPath, 'debug', name),
          `maa/${installation.label}/debug/${name}`
        )
        await yieldToEventLoop()
      }
    }
    addRecentAdapterHistoryLogs(state, dataRoots, {
      resultKey: 'maa_result',
      fallbackLatest: true,
      includeJson: false,
    })
    for (const [index, dataRoot] of dataRoots.entries()) {
      addDebugDirectory(
        state,
        path.join(dataRoot, 'debug'),
        index === 0 ? 'logs/auto-mas' : 'logs/auto-mas/backend',
        'maa',
        isLogOrImage
      )
      await yieldToEventLoop()
    }
    const runtimeDebugDir = path.join(path.dirname(process.execPath), 'debug')
    if (!dataRoots.some(root => path.resolve(root, 'debug') === path.resolve(runtimeDebugDir)))
      addDebugDirectory(state, runtimeDebugDir, 'logs/frontend-runtime', 'maa', isLogOrImage)

    for (const installation of installations) {
      await addInterfaceImages(
        state,
        path.join(installation.rootPath, 'debug', 'interface'),
        `maa/${installation.label}/debug/interface`
      )
    }
    const collectedCount = state.entries.filter(entry => entry.status !== 'skipped').length
    const incompleteCount = state.entries.filter(entry => entry.status !== 'included').length
    if (!collectedCount) return { success: false, error: '没有可导出的 MAA 日志或截图' }
    fs.mkdirSync(path.dirname(zipPath), { recursive: true })
    await state.zip.writeZipPromise(zipPath)
    logger.info(
      `MAA 日志与截图已导出: ${zipPath}，收录 ${collectedCount}，不完整 ${incompleteCount}`
    )
    return {
      success: true,
      message: incompleteCount
        ? `MAA 日志与截图已导出，收集 ${collectedCount} 个文件，${incompleteCount} 个文件缺失、被截断或未能收录`
        : `MAA 问题包导出成功，已收集 ${collectedCount} 个文件`,
      zipPath,
      incompleteCount,
    }
  } catch (error) {
    logger.error(`MAA 日志与截图导出失败: ${String(error)}`)
    return { success: false, error: 'MAA 日志与截图导出失败，请检查脚本路径、保存位置和日志后重试' }
  }
}
