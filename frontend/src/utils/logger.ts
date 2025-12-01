/**
 * 渲染进程日志工具
 * 实现新的日志API，支持模块化日志
 */

const LogLevel = {
  DEBUG: 'DEBUG',
  INFO: 'INFO',
  WARN: 'WARN',
  ERROR: 'ERROR',
} as const

export type LogLevel = (typeof LogLevel)[keyof typeof LogLevel]
export { LogLevel }

/**
 * 模块化日志器类
 */
class ModuleLogger {
  constructor(private moduleName: string) { }

  /**
   * DEBUG级别日志
   * @param message 日志消息
   * @param args 额外参数
   */
  debug(message: string, ...args: any[]): void {
    this.log(LogLevel.DEBUG, message, ...args)
  }

  /**
   * INFO级别日志
   * @param message 日志消息
   * @param args 额外参数
   */
  info(message: string, ...args: any[]): void {
    this.log(LogLevel.INFO, message, ...args)
  }

  /**
   * WARN级别日志
   * @param message 日志消息
   * @param args 额外参数
   */
  warn(message: string, ...args: any[]): void {
    this.log(LogLevel.WARN, message, ...args)
  }

  /**
   * ERROR级别日志
   * @param message 日志消息
   * @param args 额外参数
   */
  error(message: string, ...args: any[]): void {
    this.log(LogLevel.ERROR, message, ...args)
  }

  /**
   * 记录日志 - 移除了后端日志处理
   * @param level 日志级别
   * @param message 日志消息
   * @param args 额外参数
   */
  private async log(level: LogLevel, message: string, ...args: any[]): Promise<void> {
    // 格式化消息和参数
    const formattedMessage = args.length > 0 ? `${message} ${JSON.stringify(args)}` : message

    // 同时输出到控制台（保持向后兼容性）
    const consoleMethod = this.getConsoleMethod(level)
    consoleMethod(`[${this.moduleName}] ${formattedMessage}`)

    // 移除后端日志处理，只保留前端日志
    // 通过IPC发送到主进程进行统一处理
    if ((window as any).electronAPI) {
      try {
        // 只处理前端日志，不处理后端日志
        if (this.moduleName !== 'backend' && this.moduleName !== '后端') {
          await (window as any).electronAPI.logWrite(level, this.moduleName, formattedMessage)
        }
      } catch (error) {
        // 注意：这里不能使用logger，会导致循环调用
        // 使用原生console输出错误信息
        console.error('[Logger] 发送日志到主进程失败:', error)
      }
    }
  }

  /**
   * 获取对应的控制台方法
   * @param level 日志级别
   * @returns 控制台方法
   */
  private getConsoleMethod(level: LogLevel): (...args: any[]) => void {
    switch (level) {
      case LogLevel.DEBUG:
        return console.debug.bind(console)
      case LogLevel.INFO:
        return console.info.bind(console)
      case LogLevel.WARN:
        return console.warn.bind(console)
      case LogLevel.ERROR:
        return console.error.bind(console)
      default:
        return console.log.bind(console)
    }
  }
}

/**
 * 主日志器类
 */
class Logger {
  private moduleLoggers = new Map<string, ModuleLogger>()

  /**
   * 获取模块化日志器
   * @param moduleName 模块名称
   * @returns 模块化日志器实例
   */
  getModuleLogger(moduleName: string): ModuleLogger {
    if (!this.moduleLoggers.has(moduleName)) {
      this.moduleLoggers.set(moduleName, new ModuleLogger(moduleName))
    }
    return this.moduleLoggers.get(moduleName)!
  }

  /**
   * DEBUG级别日志（默认模块）
   * @param message 日志消息
   * @param args 额外参数
   */
  debug(message: string, ...args: any[]): void {
    this.getModuleLogger('前端').debug(message, ...args)
  }

  /**
   * INFO级别日志（默认模块）
   * @param message 日志消息
   * @param args 额外参数
   */
  info(message: string, ...args: any[]): void {
    this.getModuleLogger('前端').info(message, ...args)
  }

  /**
   * WARN级别日志（默认模块）
   * @param message 日志消息
   * @param args 额外参数
   */
  warn(message: string, ...args: any[]): void {
    this.getModuleLogger('前端').warn(message, ...args)
  }

  /**
   * ERROR级别日志（默认模块）
   * @param message 日志消息
   * @param args 额外参数
   */
  error(message: string, ...args: any[]): void {
    this.getModuleLogger('前端').error(message, ...args)
  }

  /**
   * 获取日志文件路径
   */
  async getLogPath(): Promise<string> {
    if ((window as any).electronAPI) {
      return await (window as any).electronAPI.getLogPath()
    }
    throw new Error('Electron API not available')
  }

  /**
   * 获取日志文件列表
   */
  async getLogFiles(): Promise<string[]> {
    if ((window as any).electronAPI) {
      return await (window as any).electronAPI.getLogFiles()
    }
    throw new Error('Electron API not available')
  }

  /**
   * 获取日志内容
   * @param lines 行数限制
   * @param fileName 文件名
   */
  async getLogs(lines?: number, fileName?: string): Promise<string> {
    if ((window as any).electronAPI) {
      return await (window as any).electronAPI.getLogs(lines, fileName)
    }
    throw new Error('Electron API not available')
  }

  /**
   * 清空日志
   * @param fileName 文件名
   */
  async clearLogs(fileName?: string): Promise<void> {
    if ((window as any).electronAPI) {
      await (window as any).electronAPI.clearLogs(fileName)
      this.info(`日志已清空: ${fileName || '当前文件'}`)
    } else {
      throw new Error('Electron API not available')
    }
  }

  /**
   * 清理旧日志
   * @param daysToKeep 保留天数
   */
  async cleanOldLogs(daysToKeep: number = 7): Promise<void> {
    if ((window as any).electronAPI) {
      await (window as any).electronAPI.cleanOldLogs()
      this.info(`已清理${daysToKeep}天前的旧日志`)
    } else {
      throw new Error('Electron API not available')
    }
  }
}

// 创建全局日志实例
export const logger = new Logger()

/**
 * 获取模块化日志器
 * @param moduleName 模块名称
 * @returns 模块化日志器实例
 */
export const getLogger = (moduleName: string): ModuleLogger => {
  return logger.getModuleLogger(moduleName)
}

// 捕获未处理的错误
window.addEventListener('error', event => {
  logger.error('未处理的错误:', event.error?.message || event.message, event.error?.stack)
})

window.addEventListener('unhandledrejection', event => {
  logger.error('未处理的Promise拒绝:', event.reason)
})

export default logger
