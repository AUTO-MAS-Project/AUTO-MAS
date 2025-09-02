// 渲染进程日志工具
interface ElectronAPI {
  getLogPath: () => Promise<string>
  getLogs: (lines?: number) => Promise<string>
  clearLogs: () => Promise<void>
  cleanOldLogs: (daysToKeep?: number) => Promise<void>
}

declare global {
  interface Window {
    electronAPI: ElectronAPI
  }
}

export enum LogLevel {
  DEBUG = 'DEBUG',
  INFO = 'INFO',
  WARN = 'WARN',
  ERROR = 'ERROR'
}

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
    if (window.electronAPI) {
      return await window.electronAPI.getLogPath()
    }
    throw new Error('Electron API not available')
  }

  // 获取日志内容
  async getLogs(lines?: number): Promise<string> {
    if (window.electronAPI) {
      return await window.electronAPI.getLogs(lines)
    }
    throw new Error('Electron API not available')
  }

  // 清空日志
  async clearLogs(): Promise<void> {
    if (window.electronAPI) {
      await window.electronAPI.clearLogs()
      console.info('日志已清空')
    } else {
      throw new Error('Electron API not available')
    }
  }

  // 清理旧日志
  async cleanOldLogs(daysToKeep: number = 7): Promise<void> {
    if (window.electronAPI) {
      await window.electronAPI.cleanOldLogs(daysToKeep)
      console.info(`已清理${daysToKeep}天前的旧日志`)
    } else {
      throw new Error('Electron API not available')
    }
  }
}

// 创建全局日志实例
export const logger = new Logger()

// 捕获未处理的错误（直接使用console，主进程会处理日志记录）
window.addEventListener('error', (event) => {
  console.error('未处理的错误:', event.error?.message || event.message, event.error?.stack)
})

window.addEventListener('unhandledrejection', (event) => {
  console.error('未处理的Promise拒绝:', event.reason)
})

export default logger