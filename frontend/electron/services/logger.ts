import log from 'electron-log'
import * as path from 'path'
import { app } from 'electron'

/**
 * 日志级别类型
 */
export type LogLevel = 'error' | 'warn' | 'info' | 'verbose' | 'debug' | 'silly'


/**
 * 模块颜色映射
 */
const moduleColors = new Map<string, string>()

/**
 * 文件日志格式化函数
 * 格式：{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {module} | {message}
 */
function fileFormat(params: { data: any[]; level: string; message: { date: Date } }): string[] {
    const time = formatTime(params.message.date)
    const level = formatLevel(params.level)
    const module = params.data[0] && typeof params.data[0] === 'string' ? params.data[0] : 'unknown'
    const message = params.data.slice(1).join(' ')

    return [`${time} | ${level} | ${module} | ${message}`]
}

/**
 * 控制台日志格式化函数
 * 格式：<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | <custom-color>{module}</custom-color> | <level>{message}</level>
 */
function consoleFormat(params: { data: any[]; level: string; message: { date: Date } }): string[] {
    const time = formatTime(params.message.date)
    const level = formatLevel(params.level)
    const module = params.data[0] && typeof params.data[0] === 'string' ? params.data[0] : 'unknown'
    const message = params.data.slice(1).join(' ')

    // 获取模块自定义颜色，默认青色
    const moduleColor = moduleColors.get(module) || '\x1b[36m'

    return [`\x1b[32m${time}\x1b[0m | ${getLevelColor(params.level)}${level}\x1b[0m | ${moduleColor}${module}\x1b[0m | ${getLevelColor(params.level)}${message}\x1b[0m`]
}

/**
 * 格式化时间
 */
function formatTime(date: Date): string {
    const year = date.getFullYear()
    const month = String(date.getMonth() + 1).padStart(2, '0')
    const day = String(date.getDate()).padStart(2, '0')
    const hours = String(date.getHours()).padStart(2, '0')
    const minutes = String(date.getMinutes()).padStart(2, '0')
    const seconds = String(date.getSeconds()).padStart(2, '0')
    const milliseconds = String(date.getMilliseconds()).padStart(3, '0')

    return `${year}-${month}-${day} ${hours}:${minutes}:${seconds}.${milliseconds}`
}

/**
 * 格式化日志级别（固定8个字符宽度）
 */
function formatLevel(level: string): string {
    return level.toUpperCase().padEnd(8, ' ')
}

/**
 * 获取日志级别对应的颜色代码
 */
function getLevelColor(level: string): string {
    switch (level) {
        case 'error':
            return '\x1b[31m' // 红色
        case 'warn':
            return '\x1b[33m' // 黄色
        case 'info':
            return '\x1b[34m' // 蓝色
        case 'verbose':
            return '\x1b[35m' // 紫色
        case 'debug':
            return '\x1b[90m' // 灰色
        case 'silly':
            return '\x1b[37m' // 白色
        default:
            return '\x1b[0m' // 默认
    }
}



/**
 * 初始化日志系统
 */
export function initializeLogger(): void {

    const appPath = path.dirname(app.getPath('exe'))

    // 设置日志级别
    log.transports.file.level = 'info'
    log.transports.console.level = 'debug'

    log.transports.file.resolvePathFn = () => path.join(appPath, 'debug', 'frontend.log')

    // 设置日志格式
    log.transports.file.format = fileFormat
    log.transports.console.format = consoleFormat

    // 设置按文件大小轮换
    log.transports.file.maxSize = 10 * 1024 * 1024 // 10MB

    log.info('日志', '日志组件初始化完成')

    // Hook console 方法
    hookConsole()
}

/**
 * 保存原始 console 方法的引用
 */
const originalConsole = {
    log: console.log,
    info: console.info,
    warn: console.warn,
    error: console.error,
    debug: console.debug,
}

/**
 * Hook console 方法，将所有 console 调用重定向到 logger 系统
 */
function hookConsole(): void {
    // Hook console.log -> log.info
    console.log = function (...args: any[]) {
        log.info('控制台', ...formatConsoleArgs(args))
    }

    // Hook console.info -> log.info
    console.info = function (...args: any[]) {
        log.info('控制台', ...formatConsoleArgs(args))
    }

    // Hook console.warn -> log.warn
    console.warn = function (...args: any[]) {
        log.warn('控制台', ...formatConsoleArgs(args))
    }

    // Hook console.error -> log.error
    console.error = function (...args: any[]) {
        log.error('控制台', ...formatConsoleArgs(args))
    }

    // Hook console.debug -> log.debug
    console.debug = function (...args: any[]) {
        log.debug('控制台', ...formatConsoleArgs(args))
    }
}

/**
 * 格式化 console 参数
 */
function formatConsoleArgs(args: any[]): any[] {
    return args.map(arg => {
        if (typeof arg === 'object' && arg !== null) {
            try {
                return JSON.stringify(arg, null, 2)
            } catch {
                return String(arg)
            }
        }
        return arg
    })
}

/**
 * 恢复原始 console 方法（用于调试或特殊情况）
 */
export function restoreConsole(): void {
    console.log = originalConsole.log
    console.info = originalConsole.info
    console.warn = originalConsole.warn
    console.error = originalConsole.error
    console.debug = originalConsole.debug
}

/**
 * 创建日志记录器
 */
export class Logger {
    private moduleName: string

    constructor(moduleName: string, moduleColor?: string) {
        this.moduleName = moduleName

        // 设置模块颜色
        if (moduleColor) {
            moduleColors.set(moduleName, moduleColor)
        }
    }

    error(message: string, ...args: unknown[]): void {
        log.error(this.moduleName, message, ...args)
    }

    warn(message: string, ...args: unknown[]): void {
        log.warn(this.moduleName, message, ...args)
    }

    info(message: string, ...args: unknown[]): void {
        log.info(this.moduleName, message, ...args)
    }

    verbose(message: string, ...args: unknown[]): void {
        log.verbose(this.moduleName, message, ...args)
    }

    debug(message: string, ...args: unknown[]): void {
        log.debug(this.moduleName, message, ...args)
    }

    silly(message: string, ...args: unknown[]): void {
        log.silly(this.moduleName, message, ...args)
    }
}

/**
 * 创建日志记录器实例
 * @param moduleName 模块名称
 * @param moduleColor 模块颜色（ANSI颜色代码），例如：'\x1b[36m'（青色）、'\x1b[33m'（黄色）
 */
export function getLogger(moduleName: string, moduleColor?: string): Logger {
    return new Logger(moduleName, moduleColor)
}

/**
 * 默认导出 electron-log 实例供直接使用
 */
export default log
