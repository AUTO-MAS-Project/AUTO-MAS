/**
 * 主进程日志服务
 * 集成格式化器、颜色处理器和文件管理器，实现统一的日志处理逻辑
 */

import { ipcMain } from 'electron'
import { LogFormatter, LogEntry } from '../utils/logFormatter'
import { ColorProcessor } from '../utils/colorProcessor'
import { LogFileManager } from '../utils/logFileManager'

export class LogService {
  private static instance: LogService
  private isInitialized = false

  private constructor() { }

  static getInstance(): LogService {
    if (!LogService.instance) {
      LogService.instance = new LogService()
    }
    return LogService.instance
  }

  /**
   * 初始化日志服务
   */
  initialize(): void {
    if (this.isInitialized) {
      return
    }

    // 确保debug目录存在
    LogFileManager.ensureDebugDir()

    // 设置定时任务：每天检查是否需要轮转日志
    this.setupRotationSchedule()

    // 注册IPC处理器
    this.registerIpcHandlers()

    // 捕获未处理的异常和Promise拒绝
    this.setupErrorHandling()

    this.isInitialized = true
    this.info('日志服务', '日志服务初始化完成')
  }

  /**
   * 设置日志轮转定时任务
   */
  private setupRotationSchedule(): void {
    // 每天凌晨2点检查是否需要轮转日志
    const now = new Date()
    const tomorrow = new Date(now)
    tomorrow.setDate(tomorrow.getDate() + 1)
    tomorrow.setHours(2, 0, 0, 0)

    const msUntilTomorrow = tomorrow.getTime() - now.getTime()

    setTimeout(() => {
      this.checkAndRotateLogs()
      // 设置每24小时执行一次
      setInterval(() => {
        this.checkAndRotateLogs()
      }, 24 * 60 * 60 * 1000)
    }, msUntilTomorrow)
  }

  /**
   * 检查并轮转日志
   */
  private async checkAndRotateLogs(): Promise<void> {
    try {
      if (LogFileManager.shouldRotate()) {
        await LogFileManager.rotateLog()
      }
      LogFileManager.cleanOldLogs()
    } catch (error) {
      this.error('日志服务', `日志轮转失败: ${error}`)
    }
  }

  /**
   * 设置错误处理
   */
  private setupErrorHandling(): void {
    process.on('uncaughtException', (error) => {
      this.error('未捕获异常', `${error.message}\n${error.stack}`)
    })

    process.on('unhandledRejection', (reason) => {
      this.error('未处理的Promise拒绝', String(reason))
    })
  }

  /**
   * 注册IPC处理器
   */
  private registerIpcHandlers(): void {
    // 在测试环境中，ipcMain可能未定义，跳过注册
    if (!ipcMain) {
      return
    }

    // 获取日志文件路径
    ipcMain.handle('log:getPath', () => {
      return LogFileManager.getCurrentLogPath()
    })

    // 获取日志文件列表
    ipcMain.handle('log:getFiles', () => {
      return LogFileManager.getLogFiles()
    })

    // 获取日志内容
    ipcMain.handle('log:getContent', (_, lines?: number, fileName?: string) => {
      return LogFileManager.getLogContent(fileName, lines)
    })

    // 清空日志
    ipcMain.handle('log:clear', (_, fileName?: string) => {
      if (!fileName || fileName === 'frontend.log') {
        LogFileManager.clearCurrentLog()
      }
    })

    // 清理旧日志
    ipcMain.handle('log:cleanOldLogs', () => {
      LogFileManager.cleanOldLogs()
    })

    // 记录日志（来自渲染进程）
    ipcMain.handle('log:write', (_, level: string, module: string, message: string) => {
      this.writeLog(level, module, message)
    })
  }

  /**
   * 写入日志
   * @param level 日志级别
   * @param module 模块名
   * @param message 日志消息
   * @param source 日志来源（可选）
   */
  writeLog(level: string, module: string, message: string, source?: string): void {

    const entry = LogFormatter.createLogEntry(level, module, message, source as any)

    // 格式化为带颜色的字符串（用于控制台输出）
    const coloredMessage = LogFormatter.formatWithColors(entry)
    const ansiMessage = ColorProcessor.htmlToAnsi(coloredMessage)

    // 输出到控制台
    console.log(ansiMessage)

    // 格式化为无颜色的字符串（用于文件存储）
    const plainMessage = LogFormatter.formatWithoutColors(entry)

    // 只有当日志级别不是 'TRACE' 或 'DEBUG' 时才写入文件（不区分大小写）
    const upperLevel = level.toUpperCase()
    if (upperLevel !== 'TRACE' && upperLevel !== 'DEBUG') {
      LogFileManager.writeLog(plainMessage)
    }
  }

  /**
   * TRACE级别日志
   * @param module 模块名
   * @param message 日志消息
   */
  trace(module: string, message: string): void {
    this.writeLog('TRACE', module, message)
  }

  /**
   * DEBUG级别日志
   * @param module 模块名
   * @param message 日志消息
   */
  debug(module: string, message: string): void {
    this.writeLog('DEBUG', module, message)
  }

  /**
   * INFO级别日志
   * @param module 模块名
   * @param message 日志消息
   */
  info(module: string, message: string): void {
    this.writeLog('INFO', module, message)
  }

  /**
   * WARN级别日志
   * @param module 模块名
   * @param message 日志消息
   */
  warn(module: string, message: string): void {
    this.writeLog('WARN', module, message)
  }

  /**
   * ERROR级别日志
   * @param module 模块名
   * @param message 日志消息
   */
  error(module: string, message: string): void {
    this.writeLog('ERROR', module, message)
  }

  /**
   * CRITICAL级别日志
   * @param module 模块名
   * @param message 日志消息
   */
  critical(module: string, message: string): void {
    this.writeLog('CRITICAL', module, message)
  }

  /**
   * SUCCESS级别日志
   * @param module 模块名
   * @param message 日志消息
   */
  success(module: string, message: string): void {
    this.writeLog('SUCCESS', module, message)
  }

  /**
   * 获取日志文件路径
   */
  getLogPath(): string {
    return LogFileManager.getCurrentLogPath()
  }

  /**
   * 获取日志文件列表
   */
  getLogFiles(): string[] {
    return LogFileManager.getLogFiles()
  }

  /**
   * 获取日志内容
   * @param lines 行数限制
   * @param fileName 文件名
   */
  getLogContent(lines?: number, fileName?: string): string {
    return LogFileManager.getLogContent(fileName, lines)
  }

  /**
   * 清空日志
   * @param fileName 文件名
   */
  clearLogs(fileName?: string): void {
    if (!fileName || fileName === 'frontend.log') {
      LogFileManager.clearCurrentLog()
    }
  }

  /**
   * 清理旧日志
   */
  cleanOldLogs(): void {
    LogFileManager.cleanOldLogs()
  }
}

// 导出单例实例
export const logService = LogService.getInstance()

// 导出便捷函数
export const setupLogger = () => logService.initialize()
export const trace = (module: string, message: string) => logService.trace(module, message)
export const debug = (module: string, message: string) => logService.debug(module, message)
export const info = (module: string, message: string) => logService.info(module, message)
export const warn = (module: string, message: string) => logService.warn(module, message)
export const error = (module: string, message: string) => logService.error(module, message)
export const critical = (module: string, message: string) => logService.critical(module, message)
export const success = (module: string, message: string) => logService.success(module, message)
export const getLogPath = () => logService.getLogPath()
export const getLogFiles = () => logService.getLogFiles()
export const getLogs = (lines?: number, fileName?: string) => logService.getLogContent(lines, fileName)
export const clearLogs = (fileName?: string) => logService.clearLogs(fileName)
export const cleanOldLogs = () => logService.cleanOldLogs()
