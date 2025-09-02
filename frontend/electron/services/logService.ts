import log from 'electron-log'
import * as path from 'path'
import { getAppRoot } from './environmentService'

// 移除ANSI颜色转义字符的函数
function stripAnsiColors(text: string): string {
  // 匹配ANSI转义序列的正则表达式 - 更完整的模式
  const ansiRegex = /\x1b\[[0-9;]*[mGKHF]|\x1b\[[\d;]*[A-Za-z]/g
  return text.replace(ansiRegex, '')
}

// 获取应用安装目录下的日志路径
function getLogDirectory(): string {
  const appRoot = getAppRoot()
  return path.join(appRoot, 'logs')
}

// 配置日志系统
export function setupLogger() {
  // 设置日志文件路径到软件安装目录
  const logPath = getLogDirectory()

  // 确保日志目录存在
  const fs = require('fs')
  if (!fs.existsSync(logPath)) {
    fs.mkdirSync(logPath, { recursive: true })
  }

  // 配置日志格式
  log.transports.file.format = '[{y}-{m}-{d} {h}:{i}:{s}.{ms}] [{level}] {text}'
  log.transports.console.format = '[{y}-{m}-{d} {h}:{i}:{s}.{ms}] [{level}] {text}'

  // 设置主进程日志文件路径和名称
  log.transports.file.resolvePathFn = () => path.join(logPath, 'app.log')

  // 设置日志级别
  log.transports.file.level = 'debug'
  log.transports.console.level = 'debug'

  // 设置文件大小限制 (10MB)
  log.transports.file.maxSize = 10 * 1024 * 1024

  // 保留最近的5个日志文件
  log.transports.file.archiveLog = (file: any) => {
    const filePath = file.toString()
    const info = path.parse(filePath)

    try {
      return path.join(info.dir, `${info.name}.old${info.ext}`)
    } catch (e) {
      console.warn('Could not archive log file', e)
      return null
    }
  }

  // 捕获未处理的异常和Promise拒绝
  log.catchErrors({
    showDialog: false,
    onError: (options: any) => {
      log.error('未处理的错误:', options.error)
      log.error('版本信息:', options.versions)
      log.error('进程类型:', options.processType)
    },
  })

  // 重写console方法，将所有控制台输出重定向到日志
  const originalConsole = {
    log: console.log,
    error: console.error,
    warn: console.warn,
    info: console.info,
    debug: console.debug,
  }

  console.log = (...args) => {
    log.info(...args)
    originalConsole.log(...args)
  }

  console.error = (...args) => {
    log.error(...args)
    originalConsole.error(...args)
  }

  console.warn = (...args) => {
    log.warn(...args)
    originalConsole.warn(...args)
  }

  console.info = (...args) => {
    log.info(...args)
    originalConsole.info(...args)
  }

  console.debug = (...args) => {
    log.debug(...args)
    originalConsole.debug(...args)
  }

  log.info('日志系统初始化完成')
  log.info(`日志文件路径: ${path.join(logPath, 'main.log')}`)

  return log
}

// 导出日志实例和工具函数
export { log, stripAnsiColors }

// 获取日志文件路径
export function getLogPath(): string {
  return path.join(getLogDirectory(), 'main.log')
}

// 清理旧日志文件
export function cleanOldLogs(daysToKeep: number = 7) {
  const fs = require('fs')
  const logDir = getLogDirectory()

  if (!fs.existsSync(logDir)) {
    return
  }

  const files = fs.readdirSync(logDir)
  const now = Date.now()
  const maxAge = daysToKeep * 24 * 60 * 60 * 1000 // 转换为毫秒

  files.forEach((file: string) => {
    const filePath = path.join(logDir, file)
    const stats = fs.statSync(filePath)

    if (now - stats.mtime.getTime() > maxAge) {
      try {
        fs.unlinkSync(filePath)
        log.info(`已删除旧日志文件: ${file}`)
      } catch (error) {
        log.error(`删除旧日志文件失败: ${file}`, error)
      }
    }
  })
}