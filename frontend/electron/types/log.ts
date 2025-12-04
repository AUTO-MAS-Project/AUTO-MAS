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
    originalLog: string
    isValid: boolean
    parseError?: string
    coloredLog?: string
}

// 日志解析器接口
export interface ILogParser {
    /**
     * 解析日志行
     * @param rawLog 原始日志行
     * @returns 解析后的日志条目
     */
    parse(rawLog: string): ParsedLogEntry

    /**
     * 检查是否能解析指定格式的日志
     * @param rawLog 原始日志行
     * @returns 是否能解析
     */
    canParse(rawLog: string): boolean

    /**
     * 获取解析器名称
     */
    getFormatName(): string

    /**
     * 获取解析器优先级（数值越高优先级越高）
     */
    getPriority(): number
}

// 日志过滤器接口
export interface ILogFilter {
    /**
     * 应用过滤器
     * @param logs 日志条目列表
     * @returns 过滤后的日志条目列表
     */
    apply(logs: ParsedLogEntry[]): ParsedLogEntry[]

    /**
     * 设置过滤条件
     * @param conditions 过滤条件
     */
    setConditions(conditions: LogFilterConditions): void
}

// 过滤条件接口
export interface LogFilterConditions {
    levels?: LogLevel[]
    modules?: string[]
    timeRange?: [Date, Date]
    keywords?: string[]
    sources?: LogSource[]
}

// 日志批处理配置
export interface LogBatchConfig {
    batchSize: number
    batchTimeout: number // 毫秒
    maxBatchSize: number
    priorityLevels: LogLevel[]
    immediateLevels: LogLevel[] // 立即处理的日志级别
}

// 日志批处理统计
export interface LogBatchStats {
    totalProcessed: number
    totalBatches: number
    averageBatchSize: number
    processingTime: number
    errorCount: number
}

// 日志缓存配置
export interface LogCacheConfig {
    maxSize: number
    ttl: number // 生存时间，毫秒
    enableLRU: boolean
    enableStats: boolean
}

// 日志缓存统计
export interface LogCacheStats {
    hits: number
    misses: number
    size: number
    maxSize: number
    hitRate: number
}

// 日志传输选项
export interface LogTransmitOptions {
    enableCompression: boolean
    enableBatching: boolean
    enablePriority: boolean
    retryCount: number
    retryDelay: number
}

// 日志处理管道配置
export interface LogPipelineConfig {
    enableCache: boolean
    enableBatching: boolean
    enableCompression: boolean
    enableFiltering: boolean
    cacheConfig?: LogCacheConfig
    batchConfig?: LogBatchConfig
    transmitOptions?: LogTransmitOptions
}

// 日志处理结果
export interface LogProcessResult {
    success: boolean
    processedCount: number
    errorCount: number
    errors: string[]
    processingTime: number
}

// 日志解析器注册信息
export interface LogParserInfo {
    name: string
    priority: number
    format: string
    enabled: boolean
    stats: {
        parseCount: number
        successCount: number
        errorCount: number
        averageTime: number
    }
}

// 日志处理统计
export interface LogProcessingStats {
    totalLogs: number
    processedLogs: number
    errorLogs: number
    averageProcessingTime: number
    cacheStats?: LogCacheStats
    batchStats?: LogBatchStats
    parserStats: LogParserInfo[]
}
