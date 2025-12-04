/**
 * 通用日志解析器
 * 用于解析各种格式的日志，作为降级方案
 */

import {
    ParsedLogEntry,
    ILogParser,
    LogLevel,
    LogSource
} from '../types/log'

/**
 * 通用日志解析器
 * 用于解析各种格式的日志，作为降级方案
 */
export class GenericLogParser implements ILogParser {
    /**
     * 检查是否能解析指定格式的日志
     * 通用解析器总是返回true，作为最后的降级方案
     */
    canParse(logLine: string): boolean {
        return !!(logLine && logLine.trim() !== '')
    }

    /**
     * 解析日志行
     */
    parse(logLine: string): ParsedLogEntry {
        const trimmedLog = logLine.trim()

        // 尝试提取时间戳
        const timestampRegex = /(\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d{3})?(?:Z|[+-]\d{2}:\d{2})?)/
        const timestampMatch = trimmedLog.match(timestampRegex)
        const timestamp = timestampMatch ? new Date(timestampMatch[1]) : new Date()

        // 尝试提取日志级别
        const levelRegex = /\b(TRACE|DEBUG|INFO|WARN|ERROR|CRITICAL|FATAL|SUCCESS)\b/i
        const levelMatch = trimmedLog.match(levelRegex)
        const level = levelMatch ? this.normalizeLogLevel(levelMatch[1]) : LogLevel.INFO

        // 尝试提取模块名
        const moduleRegex = /\[([^\]]+)\]|^(\w+)[：:]/
        const moduleMatch = trimmedLog.match(moduleRegex)
        const module = moduleMatch ? (moduleMatch[1] || moduleMatch[2]) : '系统'

        // 剩余部分作为消息
        let message = trimmedLog
        if (timestampMatch) {
            message = message.replace(timestampMatch[0], '').trim()
        }
        if (levelMatch) {
            message = message.replace(levelMatch[0], '').trim()
        }
        if (moduleMatch) {
            message = message.replace(moduleMatch[0], '').trim()
        }

        // 清理消息中的特殊字符
        message = message.replace(/^\s*[:|\-]\s*/, '').trim()

        return {
            timestamp,
            level,
            module,
            message: message || trimmedLog,
            source: LogSource.SYSTEM,
            originalLog: logLine,
            isValid: true
        }
    }

    /**
     * 标准化日志级别
     */
    private normalizeLogLevel(level: string): LogLevel {
        const normalizedLevel = level.toUpperCase()

        switch (normalizedLevel) {
            case 'TRACE':
                return LogLevel.TRACE
            case 'DEBUG':
                return LogLevel.DEBUG
            case 'INFO':
            case 'SUCCESS':
                return LogLevel.INFO
            case 'WARN':
            case 'WARNING':
                return LogLevel.WARN
            case 'ERROR':
            case 'CRITICAL':
            case 'FATAL':
                return LogLevel.ERROR
            default:
                return LogLevel.INFO
        }
    }

    /**
     * 获取解析器名称
     */
    getFormatName(): string {
        return 'GenericLogParser'
    }

    /**
     * 获取解析器优先级
     */
    getPriority(): number {
        return 1 // 最低优先级，作为最后的降级方案
    }
}