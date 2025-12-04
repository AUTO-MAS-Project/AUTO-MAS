/**
 * 后端日志解析器 - 已禁用
 * 原用于解析后端日志格式，提取时间戳、日志级别、模块名和消息内容
 * 后端日志格式: <green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | <cyan>{module}</cyan> | <level>{message}</level>
 *
 * 注意：此文件已被禁用，不再处理后端日志解析
 * GenericLogParser 已移动到 genericLogParser.ts
 */

import { LogEntry } from './logFormatter'
import {
    ParsedLogEntry,
    LogLevel,
    LogSource
} from '../types/log'

export interface ParsedBackendLog {
    timestamp?: Date
    level?: string
    module?: string
    message?: string
    coloredLog?: string
    isValid: boolean
    originalLog: string
}

// 保持向后兼容的原始BackendLogParser类
export class LegacyBackendLogParser {
    /**
     * 解析后端日志行 - 已禁用
     * @param logLine 后端日志行
     * @returns 解析后的日志对象
     */
    static parseBackendLog(logLine: string): ParsedBackendLog {
        // 禁用后端日志解析
        console.log('后端日志解析已被禁用:', logLine)

        return {
            isValid: true,
            originalLog: logLine,
            message: '后端日志解析已被禁用',
            module: '已禁用',
            level: 'INFO'
        }
    }

    /**
     * 将解析后的后端日志转换为前端LogEntry格式
     * @param parsedLog 解析后的后端日志
     * @returns 前端LogEntry对象
     */
    static toLogEntry(parsedLog: ParsedBackendLog): LogEntry {
        // 改进模块名处理逻辑
        let moduleName = parsedLog.module
        if (!moduleName || moduleName.trim() === '') {
            // 如果没有模块名，尝试从消息中提取
            const message = parsedLog.message || parsedLog.originalLog
            if (message) {
                // 尝试匹配常见的日志模式，提取可能的模块名
                const moduleMatch = message.match(/^(\w+)[：:]/)
                if (moduleMatch) {
                    moduleName = moduleMatch[1]
                } else {
                    moduleName = '后端' // 使用更合理的默认值
                }
            } else {
                moduleName = '后端' // 使用更合理的默认值
            }
        }

        return {
            timestamp: parsedLog.timestamp || new Date(),
            level: parsedLog.level || 'INFO',
            module: moduleName,
            message: parsedLog.message || parsedLog.originalLog
        }
    }

    /**
     * 直接解析后端日志并返回LogEntry - 已禁用
     * @param logLine 后端日志行
     * @returns LogEntry对象
     */
    static parseToLogEntry(logLine: string): LogEntry {
        // 禁用后端日志解析
        console.log('后端日志解析已被禁用:', logLine)

        return {
            timestamp: new Date(),
            level: 'INFO',
            module: '已禁用',
            message: '后端日志解析已被禁用'
        }
    }

    /**
     * 去除ANSI颜色代码
     * @param str 包含ANSI颜色代码的字符串
     * @returns 去除颜色代码后的字符串
     */
    private static stripAnsiColors(str: string): string {
        return str.replace(/\x1b\[[0-9;]*m/g, '')
    }

    /**
     * 判断日志行是否为后端日志格式 - 已禁用
     * @param logLine 日志行
     * @returns 是否为后端日志格式
     */
    static isBackendLogFormat(logLine: string): boolean {
        // 禁用后端日志格式检查
        console.log('后端日志格式检查已被禁用')
        return false
    }

    /**
     * 提取日志级别
     * @param logLine 日志行
     * @returns 日志级别，如果不是标准格式则返回undefined
     */
    static extractLogLevel(logLine: string): string | undefined {
        const parsed = this.parseBackendLog(logLine)
        return parsed.level
    }

    /**
     * 提取模块名
     * @param logLine 日志行
     * @returns 模块名，如果不是标准格式则返回undefined
     */
    static extractModule(logLine: string): string | undefined {
        const parsed = this.parseBackendLog(logLine)
        return parsed.module
    }

    /**
     * 提取消息内容
     * @param logLine 日志行
     * @returns 消息内容
     */
    static extractMessage(logLine: string): string {
        const parsed = this.parseBackendLog(logLine)
        return parsed.message || logLine
    }
}

// 为了向后兼容，导出原始的BackendLogParser类
export const BackendLogParserCompat = {
    parseBackendLog: (logLine: string) => LegacyBackendLogParser.parseBackendLog(logLine),
    toLogEntry: (parsedLog: ParsedBackendLog) => LegacyBackendLogParser.toLogEntry(parsedLog),
    parseToLogEntry: (logLine: string) => LegacyBackendLogParser.parseToLogEntry(logLine),
    isBackendLogFormat: (logLine: string) => LegacyBackendLogParser.isBackendLogFormat(logLine),
    extractLogLevel: (logLine: string) => LegacyBackendLogParser.extractLogLevel(logLine),
    extractModule: (logLine: string) => LegacyBackendLogParser.extractModule(logLine),
    extractMessage: (logLine: string) => LegacyBackendLogParser.extractMessage(logLine)
}

// 默认导出新的BackendLogParser实例
export const BackendLogParser = BackendLogParserCompat
