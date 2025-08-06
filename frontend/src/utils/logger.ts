import { ref } from 'vue'

export type LogLevel = 'debug' | 'info' | 'warn' | 'error'

export interface LogEntry {
  timestamp: string
  level: LogLevel
  message: string
  data?: any
  component?: string
}

class Logger {
  private logs = ref<LogEntry[]>([])
  private maxLogs = 1000 // 最大日志条数
  private logToConsole = true
  private logToStorage = true

  constructor() {
    this.loadLogsFromStorage()
  }

  private formatTimestamp(): string {
    const now = new Date()
    return now.toISOString().replace('T', ' ').substring(0, 19)
  }

  private addLog(level: LogLevel, message: string, data?: any, component?: string) {
    const logEntry: LogEntry = {
      timestamp: this.formatTimestamp(),
      level,
      message,
      data,
      component
    }

    // 添加到内存日志
    this.logs.value.push(logEntry)

    // 限制日志数量
    if (this.logs.value.length > this.maxLogs) {
      this.logs.value.shift()
    }

    // 输出到控制台
    if (this.logToConsole) {
      const consoleMessage = `[${logEntry.timestamp}] [${level.toUpperCase()}] ${component ? `[${component}] ` : ''}${message}`
      
      switch (level) {
        case 'debug':
          console.debug(consoleMessage, data)
          break
        case 'info':
          console.info(consoleMessage, data)
          break
        case 'warn':
          console.warn(consoleMessage, data)
          break
        case 'error':
          console.error(consoleMessage, data)
          break
      }
    }

    // 保存到本地存储
    if (this.logToStorage) {
      this.saveLogsToStorage()
    }
  }

  private saveLogsToStorage() {
    try {
      const logsToSave = this.logs.value.slice(-500) // 只保存最近500条日志
      localStorage.setItem('app-logs', JSON.stringify(logsToSave))
    } catch (error) {
      console.error('保存日志到本地存储失败:', error)
    }
  }

  private loadLogsFromStorage() {
    try {
      const savedLogs = localStorage.getItem('app-logs')
      if (savedLogs) {
        const parsedLogs = JSON.parse(savedLogs) as LogEntry[]
        this.logs.value = parsedLogs
      }
    } catch (error) {
      console.error('从本地存储加载日志失败:', error)
    }
  }

  // 公共方法
  debug(message: string, data?: any, component?: string) {
    this.addLog('debug', message, data, component)
  }

  info(message: string, data?: any, component?: string) {
    this.addLog('info', message, data, component)
  }

  warn(message: string, data?: any, component?: string) {
    this.addLog('warn', message, data, component)
  }

  error(message: string, data?: any, component?: string) {
    this.addLog('error', message, data, component)
  }

  // 获取日志
  getLogs() {
    return this.logs
  }

  // 清空日志
  clearLogs() {
    this.logs.value = []
    localStorage.removeItem('app-logs')
  }

  // 导出日志到文件
  exportLogs(): string {
    const logText = this.logs.value
      .map(log => {
        const dataStr = log.data ? ` | Data: ${JSON.stringify(log.data)}` : ''
        const componentStr = log.component ? ` | Component: ${log.component}` : ''
        return `[${log.timestamp}] [${log.level.toUpperCase()}]${componentStr} ${log.message}${dataStr}`
      })
      .join('\n')
    
    return logText
  }

  // 下载日志文件
  downloadLogs() {
    const logText = this.exportLogs()
    const blob = new Blob([logText], { type: 'text/plain;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    
    const link = document.createElement('a')
    link.href = url
    link.download = `auto-maa-logs-${new Date().toISOString().split('T')[0]}.txt`
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    
    URL.revokeObjectURL(url)
  }

  // 配置选项
  setLogToConsole(enabled: boolean) {
    this.logToConsole = enabled
  }

  setLogToStorage(enabled: boolean) {
    this.logToStorage = enabled
  }

  setMaxLogs(max: number) {
    this.maxLogs = max
    if (this.logs.value.length > max) {
      this.logs.value = this.logs.value.slice(-max)
    }
  }
}

// 创建全局日志实例
export const logger = new Logger()

// 创建组件专用的日志器
export function createComponentLogger(componentName: string) {
  return {
    debug: (message: string, data?: any) => logger.debug(message, data, componentName),
    info: (message: string, data?: any) => logger.info(message, data, componentName),
    warn: (message: string, data?: any) => logger.warn(message, data, componentName),
    error: (message: string, data?: any) => logger.error(message, data, componentName),
  }
}

// Vue插件
export default {
  install(app: any) {
    app.config.globalProperties.$logger = logger
    app.provide('logger', logger)
  }
}