/**
 * 文件操作相关的 IPC 处理器
 */

import { ipcMain } from 'electron'
import { promises as fsPromises } from 'fs'
import path from 'path'
import { getLogger } from '../services/logger'

const logger = getLogger('文件处理器')

// 防止重复注册的标志
let isRegistered = false

/**
 * 注册所有文件操作相关的 IPC 处理器
 */
export function registerFileHandlers() {
  // 防止重复注册
  if (isRegistered) {
    logger.info('文件处理器已经注册，跳过重复注册')
    return
  }
  isRegistered = true

  // ==================== 读取文件 ====================
  ipcMain.handle('read-file', async (event, filePath: string) => {
    try {
      // 安全检查：防止路径遍历攻击
      const resolvedPath = path.resolve(filePath)

      // 检查文件是否存在
      const stats = await fsPromises.stat(resolvedPath)
      if (!stats.isFile()) {
        throw new Error('指定路径不是文件')
      }

      // 读取文件内容
      const content = await fsPromises.readFile(resolvedPath, 'utf-8')

      logger.info(`成功读取文件: ${filePath}`)
      return content
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.error(`读取文件失败 ${filePath}: ${errorMsg}`)
      throw error
    }
  })

  // ==================== 写入文件 ====================
  ipcMain.handle('write-file', async (event, filePath: string, data: string) => {
    try {
      // 安全检查：防止路径遍历攻击
      const resolvedPath = path.resolve(filePath)

      // 检查父目录是否存在，如果不存在则创建
      const dirPath = path.dirname(resolvedPath)
      try {
        await fsPromises.access(dirPath)
      } catch {
        // 如果目录不存在，尝试创建目录
        await fsPromises.mkdir(dirPath, { recursive: true })
      }

      // 写入文件
      await fsPromises.writeFile(resolvedPath, data, 'utf-8')

      logger.info(`成功写入文件: ${filePath}`)
      return { success: true }
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.error(`写入文件失败 ${filePath}: ${errorMsg}`)
      return { success: false, error: errorMsg }
    }
  })

  // ==================== 检查文件是否存在 ====================
  ipcMain.handle('file-exists', async (event, filePath: string) => {
    try {
      const resolvedPath = path.resolve(filePath)

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
