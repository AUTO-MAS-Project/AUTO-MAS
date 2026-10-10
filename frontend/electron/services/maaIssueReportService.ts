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
  addSkippedEntry,
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
  zipPath?: string
  collectedCount?: number
  errorCode?: 'no-installation' | 'no-files' | 'export-failed'
  /** 有文件缺失、被截断或未能收录时大于 0，界面按警告样式提示 */
  incompleteCount?: number
}

/** 逐个收录大文件时让主进程处理窗口事件。 */
const yieldToEventLoop = () => new Promise<void>(resolve => setImmediate(resolve))

/** 只收给定目录中的最新一张截图，保留原来的归档路径。 */
async function addLatestImage(
  state: CollectorState,
  directories: Array<{ sourceDir: string; archiveDir: string }>
): Promise<void> {
  let latest: { sourcePath: string; archivePath: string; mtimeMs: number } | undefined
  for (const { sourceDir, archiveDir } of directories) {
    addDirectory(state, sourceDir, archiveDir, {
      includeFile: isImage,
      addFile: (_, sourcePath, archivePath) => {
        try {
          const mtimeMs = fs.statSync(sourcePath).mtimeMs
          if (
            !latest ||
            mtimeMs > latest.mtimeMs ||
            (mtimeMs === latest.mtimeMs && archivePath < latest.archivePath)
          )
            latest = { sourcePath, archivePath, mtimeMs }
        } catch {
          addSkippedEntry(state, archivePath, 0, '截图已消失或无法读取')
        }
      },
    })
  }
  if (!latest) return
  const before = state.entries.length
  addDiagnosticFile(state, latest.sourcePath, latest.archivePath)
  if (state.entries.length === before)
    addSkippedEntry(state, latest.archivePath, 0, '截图已消失或无法读取')
  await yieldToEventLoop()
}

/** 失败截图单独选最新一张，避免递归收集时把旧图一起带入。 */
function addRuntimeDebugDirectory(
  state: CollectorState,
  sourceDir: string,
  archiveDir: string
): void {
  addDebugDirectory(
    state,
    sourceDir,
    archiveDir,
    'maa',
    filePath =>
      isLogOrImage(filePath) &&
      !(
        isImage(filePath) && path.relative(sourceDir, filePath).split(path.sep)[0] === 'maa-failure'
      )
  )
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
    if (!installations.length) return { success: false, errorCode: 'no-installation' }

    // 每个安装的核心日志优先，各安装依次收同类文件。.bak 未轮转属常态，缺失
    // 保持静默；存在却收不进来（被占用、权限等）要记成 skipped，让清单与
    // incompleteCount 知道少了什么。
    for (const name of PRIMARY_LOGS) {
      for (const installation of installations) {
        const sourcePath = path.join(installation.rootPath, 'debug', name)
        if (!fs.existsSync(sourcePath)) continue
        const archivePath = `maa/${installation.label}/debug/${name}`
        const before = state.entries.length
        addDiagnosticFile(state, sourcePath, archivePath)
        if (state.entries.length === before)
          addSkippedEntry(state, archivePath, 0, '核心日志无法读取')
        await yieldToEventLoop()
      }
    }
    addRecentAdapterHistoryLogs(state, dataRoots, {
      resultKey: 'maa_result',
      fallbackLatest: true,
      includeJson: false,
    })
    const debugDirectories = dataRoots.map((dataRoot, index) => ({
      sourceDir: path.join(dataRoot, 'debug'),
      archiveDir: index === 0 ? 'logs/auto-mas' : 'logs/auto-mas/backend',
    }))
    for (const directory of debugDirectories) {
      addRuntimeDebugDirectory(state, directory.sourceDir, directory.archiveDir)
      await yieldToEventLoop()
    }
    const runtimeDebugDir = path.join(path.dirname(process.execPath), 'debug')
    if (!dataRoots.some(root => path.resolve(root, 'debug') === path.resolve(runtimeDebugDir))) {
      debugDirectories.push({ sourceDir: runtimeDebugDir, archiveDir: 'logs/frontend-runtime' })
      addRuntimeDebugDirectory(state, runtimeDebugDir, 'logs/frontend-runtime')
    }

    await addLatestImage(
      state,
      debugDirectories.map(directory => ({
        sourceDir: path.join(directory.sourceDir, 'maa-failure'),
        archiveDir: `${directory.archiveDir}/maa-failure`,
      }))
    )
    for (const installation of installations)
      await addLatestImage(state, [
        {
          sourceDir: path.join(installation.rootPath, 'debug', 'interface'),
          archiveDir: `maa/${installation.label}/debug/interface`,
        },
      ])
    const collectedCount = state.entries.filter(entry => entry.status !== 'skipped').length
    const incompleteCount = state.entries.filter(entry => entry.status !== 'included').length
    if (!collectedCount) return { success: false, errorCode: 'no-files' }
    fs.mkdirSync(path.dirname(zipPath), { recursive: true })
    await state.zip.writeZipPromise(zipPath)
    logger.info(
      `MAA 日志与截图已导出: ${zipPath}，收录 ${collectedCount}，不完整 ${incompleteCount}`
    )
    return {
      success: true,
      collectedCount,
      zipPath,
      incompleteCount,
    }
  } catch (error) {
    logger.error(`MAA 日志与截图导出失败: ${String(error)}`)
    return { success: false, errorCode: 'export-failed' }
  }
}
