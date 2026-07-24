/**
 * 文件操作相关的 IPC 处理器
 */

import { BrowserWindow, dialog, ipcMain } from 'electron'
import { promises as fsPromises } from 'fs'
import {
  hasRendererReadGrant,
  isLegacyRendererTextPath,
  MAX_RENDERER_TEXT_FILE_BYTES,
  normalizeRendererGrantPath,
  resolveRendererFilePath,
} from '../services/fileAccessPolicy'
import { assertAllowedMainFrameSender } from '../services/ipcSenderPolicy'
import { getLogger } from '../services/logger'

const logger = getLogger('文件处理器')

// 防止重复注册的标志
let isRegistered = false
const grantedFiles = new Set<string>()
const grantedDirectories = new Set<string>()

/**
 * 注册所有文件操作相关的 IPC 处理器
 */
export function registerFileHandlers(getMainWindow: () => BrowserWindow | null) {
  // 防止重复注册
  if (isRegistered) {
    logger.info('文件处理器已经注册，跳过重复注册')
    return
  }
  isRegistered = true

  ipcMain.handle('select-folder', async event => {
    const parent = getMainWindow()
    assertAllowedMainFrameSender(event, [parent])
    const options: Electron.OpenDialogOptions = {
      properties: ['openDirectory'],
      title: '选择文件夹',
    }
    const result = parent
      ? await dialog.showOpenDialog(parent, options)
      : await dialog.showOpenDialog(options)
    if (result.canceled || !result.filePaths[0]) {
      return null
    }
    grantedDirectories.add(normalizeRendererGrantPath(result.filePaths[0]))
    return result.filePaths[0]
  })

  ipcMain.handle('select-file', async (event, filters: Electron.FileFilter[] = []) => {
    const parent = getMainWindow()
    assertAllowedMainFrameSender(event, [parent])
    const options: Electron.OpenDialogOptions = {
      properties: ['openFile'],
      title: '选择文件',
      filters: filters.length > 0 ? filters : [{ name: '所有文件', extensions: ['*'] }],
    }
    const result = parent
      ? await dialog.showOpenDialog(parent, options)
      : await dialog.showOpenDialog(options)
    if (result.canceled) {
      return []
    }
    result.filePaths.forEach(filePath => grantedFiles.add(normalizeRendererGrantPath(filePath)))
    return result.filePaths
  })

  // ==================== 读取文件 ====================
  ipcMain.handle('read-file', async (event, filePath: string) => {
    try {
      assertAllowedMainFrameSender(event, [getMainWindow()])
      const resolvedPath = resolveRendererFilePath(filePath)

      if (
        !hasRendererReadGrant(resolvedPath, grantedFiles, grantedDirectories) &&
        !isLegacyRendererTextPath(resolvedPath)
      ) {
        throw new Error('File access requires an explicit user selection')
      }

      const stats = await fsPromises.stat(resolvedPath)
      if (!stats.isFile()) {
        throw new Error('指定路径不是文件')
      }
      if (stats.size > MAX_RENDERER_TEXT_FILE_BYTES) {
        throw new Error('文件过大，无法在界面中读取')
      }

      const content = await fsPromises.readFile(resolvedPath, 'utf-8')

      logger.info(`成功读取文件: ${filePath}`)
      return content
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.error(`读取文件失败 ${filePath}: ${errorMsg}`)
      throw error
    }
  })

  // ==================== 检查文件是否存在 ====================
  ipcMain.handle('file-exists', async (event, filePath: string) => {
    try {
      assertAllowedMainFrameSender(event, [getMainWindow()])
      const resolvedPath = resolveRendererFilePath(filePath)

      try {
        await fsPromises.access(resolvedPath)
        return true
      } catch {
        return false
      }
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.error(`检查文件存在性失败 ${filePath}: ${errorMsg}`)
      return false
    }
  })
}
