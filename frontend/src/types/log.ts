/**
 * 日志系统类型定义
 * 统一日志条目接口和相关类型
 */

// 日志级别枚举
export enum LogLevel {
    TRACE = 'TRACE',
    DEBUG = 'DEBUG',
    INFO = 'INFO',
    WARN = 'WARN',
    ERROR = 'ERROR',
    CRITICAL = 'CRITICAL',
    SUCCESS = 'SUCCESS'
}

// 日志来源枚举
export enum LogSource {
    BACKEND = 'backend',
    FRONTEND = 'frontend',
    SYSTEM = 'system'
}

// 基础日志条目接口
export interface LogEntry {
    timestamp: Date
    level: LogLevel
    module: string
    message: string
    source?: LogSource
    metadata?: Record<string, any>
}

// 解析后的日志条目接口
export interface ParsedLogEntry extends LogEntry {
    id?: string
    originalLog: string
    isValid: boolean
    parseError?: string
    coloredLog?: string
}

// 过滤条件接口
export interface LogFilterConditions {
    levels?: LogLevel[]
    modules?: string[]
    timeRange?: [Date, Date]
    keywords?: string[]
    sources?: LogSource[]
}
