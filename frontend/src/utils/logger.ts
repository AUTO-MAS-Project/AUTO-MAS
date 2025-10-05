// 渲染进程日志工具
const LogLevel = {
  DEBUG: 'DEBUG',
  INFO: 'INFO',
  WARN: 'WARN',
  ERROR: 'ERROR',
} as const

export type LogLevel = (typeof LogLevel)[keyof typeof LogLevel]
export { LogLevel }

class Logger {
  // 直接使用原生console，主进程会自动处理日志记录
  debug(message: string, ...args: any[]) {
    console.debug(message, ...args)
  }

  info(message: string, ...args: any[]) {
    console.info(message, ...args)
  }

  warn(message: string, ...args: any[]) {
    console.warn(message, ...args)
  }

  error(message: string, ...args: any[]) {
    console.error(message, ...args)
  }

  // 获取日志文件路径
  async getLogPath(): Promise<string> {
    if ((window as any).electronAPI) {
      return await (window as any).electronAPI.getLogPath()
    }
    throw new Error('Electron API not available')
  }

  // 获取日志文件列表
  async getLogFiles(): Promise<string[]> {
    if ((window as any).electronAPI) {
      return await (window as any).electronAPI.getLogFiles()
    }
    throw new Error('Electron API not available')
  }

  // 获取日志内容
  async getLogs(lines?: number, fileName?: string): Promise<string> {
    if ((window as any).electronAPI) {
      return await (window as any).electronAPI.getLogs(lines, fileName)
    }
    throw new Error('Electron API not available')
  }

  // 清空日志
  async clearLogs(fileName?: string): Promise<void> {
    if ((window as any).electronAPI) {
      await (window as any).electronAPI.clearLogs(fileName)
      console.info(`日志已清空: ${fileName || '当前文件'}`)
    } else {
      throw new Error('Electron API not available')
    }
  }

  // 清理旧日志
  async cleanOldLogs(daysToKeep: number = 7): Promise<void> {
    if ((window as any).electronAPI) {
      await (window as any).electronAPI.cleanOldLogs(daysToKeep)
      console.info(`已清理${daysToKeep}天前的旧日志`)
    } else {
      throw new Error('Electron API not available')
    }
  }
}

// 创建全局日志实例
export const logger = new Logger()

// 捕获未处理的错误（直接使用console，主进程会处理日志记录）
window.addEventListener('error', event => {
  console.error('未处理的错误:', event.error?.message || event.message, event.error?.stack)
})

window.addEventListener('unhandledrejection', event => {
  console.error('未处理的Promise拒绝:', event.reason)
})

export default logger
