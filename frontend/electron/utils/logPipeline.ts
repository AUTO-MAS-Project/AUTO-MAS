/**
 * 统一日志处理管道
 * 实现解析器注册、缓存机制和批处理功能
 */

import {
    ParsedLogEntry,
    ILogParser,
    LogSource,
    LogPipelineConfig,
    LogProcessResult,
    LogProcessingStats,
    LogCacheConfig,
    LogCacheStats,
    LogParserInfo
} from '../types/log'
import { LogBatchProcessor, createDefaultBatchConfig } from './logBatchProcessor'
import { LogFormatter } from './logFormatter'

export class LogPipeline {
    private static instance: LogPipeline | null = null
    private parsers: ILogParser[] = []
    private cache: Map<string, ParsedLogEntry> = new Map()
    private batchProcessor: LogBatchProcessor
    private config: LogPipelineConfig
    private outputCallback?: (log: string) => void
    private stats: LogProcessingStats = {
        totalLogs: 0,
        processedLogs: 0,
        errorLogs: 0,
        averageProcessingTime: 0,
        parserStats: []
    }
    private cacheStats: LogCacheStats = {
        hits: 0,
        misses: 0,
        size: 0,
        maxSize: 0,
        hitRate: 0
    }

    // 性能优化：缓存热路径
    private cacheHotPath = new Map<string, boolean>()
    private lastCacheCleanup = 0

    private constructor(config?: LogPipelineConfig) {
        this.config = {
            enableCache: true,
            enableBatching: true,
            enableCompression: false,
            enableFiltering: false,
            cacheConfig: {
                maxSize: 1000,
                ttl: 300000, // 5分钟
                enableLRU: true,
                enableStats: true
            },
            batchConfig: createDefaultBatchConfig(),
            transmitOptions: {
                enableCompression: false,
                enableBatching: true,
                enablePriority: true,
                retryCount: 3,
                retryDelay: 1000
            },
            ...config
        }

        // 初始化批处理器
        this.batchProcessor = new LogBatchProcessor(
            this.config.batchConfig!,
            this.processBatch.bind(this)
        )

        // 更新缓存最大大小
        if (this.config.cacheConfig) {
            this.cacheStats.maxSize = this.config.cacheConfig.maxSize
        }
    }

    /**
     * 获取单例实例
     */
    static getInstance(config?: LogPipelineConfig): LogPipeline {
        if (!LogPipeline.instance) {
            LogPipeline.instance = new LogPipeline(config)
        }
        return LogPipeline.instance
    }

    /**
     * 注册日志解析器
     * @param parser 日志解析器
     */
    registerParser(parser: ILogParser): void {
        this.parsers.push(parser)
        // 按优先级排序
        this.parsers.sort((a, b) => b.getPriority() - a.getPriority())

        // 初始化解析器统计信息
        this.stats.parserStats.push({
            name: parser.getFormatName(),
            priority: parser.getPriority(),
            format: parser.getFormatName(),
            enabled: true,
            stats: {
                parseCount: 0,
                successCount: 0,
                errorCount: 0,
                averageTime: 0
            }
        })
    }

    /**
     * 设置输出回调
     * @param callback 输出回调函数
     */
    setOutputCallback(callback: (log: string) => void): void {
        this.outputCallback = callback
    }

    /**
     * 处理日志
     * @param rawLog 原始日志
     * @param source 日志来源
     */
    async processLog(rawLog: string, source: LogSource = LogSource.SYSTEM): Promise<LogProcessResult> {
        const startTime = performance.now()
        const result: LogProcessResult = {
            success: false,
            processedCount: 0,
            errorCount: 0,
            errors: [],
            processingTime: 0
        }

        try {
            if (!rawLog || rawLog.trim() === '') {
                // 错误处理增强：记录空日志
                this.debugLog('processLog', '收到空日志，跳过处理', {
                    source,
                    logLength: rawLog?.length || 0
                })
                return result
            }

            this.stats.totalLogs++

            // 性能优化：快速路径检查
            if (this.cacheHotPath.has(rawLog)) {
                result.success = true
                result.processedCount = 1
                this.stats.processedLogs++
                result.processingTime = performance.now() - startTime
                this.debugLog('processLog', '使用快速路径处理日志', {
                    cacheHit: true,
                    processingTime: result.processingTime
                })
                return result
            }

            // 检查缓存
            let parsedLog: ParsedLogEntry | undefined
            const cacheKey = this.generateCacheKey(rawLog, source)

            if (this.config.enableCache) {
                try {
                    parsedLog = this.getFromCache(cacheKey)
                    if (parsedLog) {
                        this.cacheStats.hits++
                        this.cacheHotPath.set(rawLog, true)
                        this.debugLog('processLog', '缓存命中', {
                            cacheKey,
                            logLevel: parsedLog.level
                        })
                    } else {
                        this.cacheStats.misses++
                        this.debugLog('processLog', '缓存未命中', {
                            cacheKey
                        })
                    }
                } catch (cacheError) {
                    this.errorLog('processLog', '缓存访问失败', {
                        cacheKey,
                        error: cacheError instanceof Error ? cacheError.message : String(cacheError)
                    })
                    // 继续处理，不中断流程
                }
            }

            // 如果缓存中没有，则解析
            if (!parsedLog) {
                try {
                    parsedLog = this.parseLog(rawLog, source) || undefined

                    if (parsedLog) {
                        this.debugLog('processLog', '日志解析成功', {
                            cacheKey,
                            logLevel: parsedLog.level,
                            module: parsedLog.module
                        })
                    }
                } catch (parseError) {
                    this.errorLog('processLog', '日志解析异常', {
                        cacheKey,
                        rawLog: rawLog.substring(0, 200), // 只记录前200字符避免日志过长
                        error: parseError instanceof Error ? parseError.message : String(parseError),
                        stack: parseError instanceof Error ? parseError.stack : undefined
                    })
                    // 创建降级日志条目
                    parsedLog = this.createFallbackLogEntry(rawLog, source)
                }

                // 存储到缓存
                if (this.config.enableCache && parsedLog) {
                    try {
                        this.setToCache(cacheKey, parsedLog)
                    } catch (cacheStoreError) {
                        this.warnLog('processLog', '缓存存储失败', {
                            cacheKey,
                            error: cacheStoreError instanceof Error ? cacheStoreError.message : String(cacheStoreError)
                        })
                        // 继续处理，不中断流程
                    }
                }
            }

            if (!parsedLog || !parsedLog.isValid) {
                const errorMessage = `解析失败: ${rawLog.substring(0, 100)}`
                result.errorCount++
                result.errors.push(errorMessage)
                this.stats.errorLogs++
                this.errorLog('processLog', '日志解析失败', {
                    rawLog: rawLog.substring(0, 200),
                    cacheKey,
                    parsedLog: parsedLog ? {
                        isValid: parsedLog.isValid,
                        level: parsedLog.level
                    } : null
                })
                return result
            }

            // 设置日志来源
            parsedLog.source = source

            // 处理解析后的日志
            try {
                await this.processParsedLog(parsedLog)
            } catch (processError) {
                this.errorLog('processLog', '日志后处理失败', {
                    cacheKey,
                    logLevel: parsedLog.level,
                    error: processError instanceof Error ? processError.message : String(processError)
                })
                // 不中断流程，继续返回成功结果
            }

            result.success = true
            result.processedCount = 1
            this.stats.processedLogs++

        } catch (error) {
            const errorMessage = `处理异常: ${error instanceof Error ? error.message : String(error)}`
            result.errorCount++
            result.errors.push(errorMessage)
            this.stats.errorLogs++
            this.errorLog('processLog', '日志处理异常', {
                rawLog: rawLog.substring(0, 200),
                source,
                error: error instanceof Error ? {
                    message: error.message,
                    stack: error.stack
                } : String(error)
            })
        } finally {
            result.processingTime = performance.now() - startTime
            this.updateAverageProcessingTime(result.processingTime)

            // 性能优化：定期清理缓存热路径
            this.periodicCacheCleanup()

            // 性能监控：记录慢处理
            if (result.processingTime > 10) {
                this.warnLog('processLog', '日志处理耗时过长', {
                    processingTime: result.processingTime,
                    rawLogLength: rawLog.length
                })
            }
        }

        return result
    }

    /**
     * 解析日志
     * @param rawLog 原始日志
     * @param source 日志来源
     */
    private parseLog(rawLog: string, source: LogSource): ParsedLogEntry | null {
        for (const parser of this.parsers) {
            const startTime = performance.now()

            try {
                if (parser.canParse(rawLog)) {
                    const parsedLog = parser.parse(rawLog)

                    // 更新解析器统计信息
                    const parserStat = this.stats.parserStats.find(stat => stat.name === parser.getFormatName())
                    if (parserStat) {
                        parserStat.stats.parseCount++
                        if (parsedLog && parsedLog.isValid) {
                            parserStat.stats.successCount++
                        } else {
                            parserStat.stats.errorCount++
                        }

                        const processingTime = performance.now() - startTime
                        parserStat.stats.averageTime =
                            (parserStat.stats.averageTime * (parserStat.stats.parseCount - 1) + processingTime) /
                            parserStat.stats.parseCount

                        // 性能监控：记录慢解析
                        if (processingTime > 5) {
                            this.warnLog('parseLog', '解析器处理耗时过长', {
                                parser: parser.getFormatName(),
                                processingTime,
                                rawLogLength: rawLog.length
                            })
                        }
                    }

                    if (parsedLog) {
                        this.debugLog('parseLog', '解析器成功解析日志', {
                            parser: parser.getFormatName(),
                            logLevel: parsedLog.level,
                            isValid: parsedLog.isValid
                        })
                    }

                    return parsedLog
                }
            } catch (error) {
                // 更新错误统计
                const parserStat = this.stats.parserStats.find(stat => stat.name === parser.getFormatName())
                if (parserStat) {
                    parserStat.stats.parseCount++
                    parserStat.stats.errorCount++
                }

                this.errorLog('parseLog', `解析器 ${parser.getFormatName()} 解析失败`, {
                    rawLog: rawLog.substring(0, 200),
                    error: error instanceof Error ? {
                        message: error.message,
                        stack: error.stack
                    } : String(error),
                    parser: parser.getFormatName(),
                    priority: parser.getPriority()
                })
            }
        }

        // 如果没有解析器能够处理，创建一个基本的日志条目
        const fallbackLog = this.createFallbackLogEntry(rawLog, source)
        this.debugLog('parseLog', '使用降级日志条目', {
            source,
            logLevel: fallbackLog.level
        })
        return fallbackLog
    }

    /**
     * 创建降级日志条目
     * @param rawLog 原始日志
     * @param source 日志来源
     */
    private createFallbackLogEntry(rawLog: string, source: LogSource): ParsedLogEntry {
        return {
            timestamp: new Date(),
            level: 'INFO' as any,
            module: source === LogSource.FRONTEND ? '前端' : '系统',
            message: rawLog,
            source,
            originalLog: rawLog,
            isValid: true
        }
    }

    /**
     * 处理解析后的日志
     * @param parsedLog 解析后的日志
     */
    private async processParsedLog(parsedLog: ParsedLogEntry): Promise<void> {
        // 如果启用批处理，添加到批处理器
        if (this.config.enableBatching) {
            this.batchProcessor.addLog(parsedLog)
        } else {
            // 直接处理
            this.outputSingleLog(parsedLog)
        }
    }

    /**
     * 处理批次日志
     * @param logs 日志批次
     */
    private processBatch(logs: ParsedLogEntry[]): void {
        try {
            // 格式化并发送批次日志
            const formattedLogs = logs.map(log => this.formatLog(log))

            if (this.outputCallback) {
                formattedLogs.forEach(formattedLog => {
                    this.outputCallback?.(formattedLog)
                })
            }
        } catch (error) {
            console.error('批处理日志失败:', error)
        }
    }

    /**
     * 输出单个日志
     * @param parsedLog 解析后的日志
     */
    private outputSingleLog(parsedLog: ParsedLogEntry): void {
        try {
            const formattedLog = this.formatLog(parsedLog)

            if (this.outputCallback) {
                this.outputCallback(formattedLog)
            }
        } catch (error) {
            console.error('输出单个日志失败:', error)
        }
    }

    /**
     * 格式化日志
     * @param parsedLog 解析后的日志
     */
    private formatLog(parsedLog: ParsedLogEntry): string {
        // 如果有带颜色的日志，直接使用
        if (parsedLog.coloredLog) {
            return parsedLog.coloredLog
        }

        // 否则使用LogFormatter格式化
        const logEntry = {
            timestamp: parsedLog.timestamp,
            level: parsedLog.level,
            module: parsedLog.module,
            message: parsedLog.message
        }

        return LogFormatter.formatWithColors(logEntry)
    }

    /**
     * 生成缓存键
     * @param rawLog 原始日志
     * @param source 日志来源
     */
    private generateCacheKey(rawLog: string, source: LogSource): string {
        // 使用简单的哈希函数生成键
        const hash = this.simpleHash(rawLog + source)
        return `${source}_${hash}`
    }

    /**
     * 简单哈希函数
     * @param str 字符串
     */
    private simpleHash(str: string): string {
        let hash = 0
        for (let i = 0; i < str.length; i++) {
            const char = str.charCodeAt(i)
            hash = ((hash << 5) - hash) + char
            hash = hash & hash // 转换为32位整数
        }
        return Math.abs(hash).toString(36)
    }

    /**
     * 从缓存获取日志
     * @param key 缓存键
     */
    private getFromCache(key: string): ParsedLogEntry | undefined {
        return this.cache.get(key)
    }

    /**
     * 设置缓存
     * @param key 缓存键
     * @param value 日志条目
     */
    private setToCache(key: string, value: ParsedLogEntry): void {
        // 检查缓存大小限制
        if (this.cache.size >= (this.config.cacheConfig?.maxSize || 1000)) {
            this.evictCache()
        }

        this.cache.set(key, value)
        this.cacheStats.size = this.cache.size
    }

    // 性能优化：定期清理缓存热路径
    private periodicCacheCleanup(): void {
        const now = Date.now()
        // 每5分钟清理一次热路径缓存
        if (now - this.lastCacheCleanup > 300000) {
            // 保留最近使用的1000个条目
            if (this.cacheHotPath.size > 1000) {
                const entries = Array.from(this.cacheHotPath.entries())
                this.cacheHotPath.clear()
                // 保留后500个条目
                for (let i = Math.max(0, entries.length - 500); i < entries.length; i++) {
                    this.cacheHotPath.set(entries[i][0], true)
                }
            }
            this.lastCacheCleanup = now
        }
    }

    /**
     * 缓存淘汰
     */
    private evictCache(): void {
        if (!this.config.cacheConfig?.enableLRU) {
            // 性能优化：批量FIFO淘汰，删除最早的条目
            const keysToDelete = Array.from(this.cache.keys()).slice(0, Math.floor(this.cache.size * 0.1))
            keysToDelete.forEach(key => {
                this.cache.delete(key)
                this.cacheHotPath.delete(key)
            })
        } else {
            // 性能优化：更高效的LRU淘汰
            const keysToDelete = Array.from(this.cache.keys()).slice(0, Math.floor(this.cache.size * 0.25))
            keysToDelete.forEach(key => {
                this.cache.delete(key)
                this.cacheHotPath.delete(key)
            })
        }
    }

    /**
     * 更新平均处理时间
     * @param processingTime 处理时间
     */
    private updateAverageProcessingTime(processingTime: number): void {
        if (this.stats.totalLogs === 0) {
            this.stats.averageProcessingTime = processingTime
        } else {
            this.stats.averageProcessingTime =
                (this.stats.averageProcessingTime * (this.stats.totalLogs - 1) + processingTime) /
                this.stats.totalLogs
        }
    }

    /**
     * 更新缓存统计信息
     */
    private updateCacheStats(): void {
        const total = this.cacheStats.hits + this.cacheStats.misses
        this.cacheStats.hitRate = total > 0 ? this.cacheStats.hits / total : 0
        this.cacheStats.size = this.cache.size
    }

    /**
     * 立即刷新所有待处理的日志
     */
    flush(): void {
        this.batchProcessor.flush()
    }

    /**
     * 获取统计信息
     */
    getStats(): LogProcessingStats {
        // 更新缓存统计信息
        this.updateCacheStats()

        // 更新批处理统计信息
        const batchStats = this.batchProcessor.getStats()

        return {
            ...this.stats,
            cacheStats: { ...this.cacheStats },
            batchStats
        }
    }

    /**
     * 获取配置
     */
    getConfig(): LogPipelineConfig {
        return { ...this.config }
    }

    /**
     * 更新配置
     * @param newConfig 新配置
     */
    updateConfig(newConfig: Partial<LogPipelineConfig>): void {
        this.config = { ...this.config, ...newConfig }

        // 更新批处理配置
        if (newConfig.batchConfig) {
            this.batchProcessor.updateConfig(newConfig.batchConfig)
        }

        // 更新缓存配置
        if (newConfig.cacheConfig) {
            this.cacheStats.maxSize = newConfig.cacheConfig.maxSize
        }
    }

    /**
     * 启用/禁用解析器
     * @param parserName 解析器名称
     * @param enabled 是否启用
     */
    toggleParser(parserName: string, enabled: boolean): void {
        const parserStat = this.stats.parserStats.find(stat => stat.name === parserName)
        if (parserStat) {
            parserStat.enabled = enabled
        }
    }

    /**
     * 清空缓存
     */
    clearCache(): void {
        this.cache.clear()
        this.cacheStats.size = 0
        this.cacheStats.hits = 0
        this.cacheStats.misses = 0
        this.cacheStats.hitRate = 0
    }

    /**
     * 重置统计信息
     */
    resetStats(): void {
        this.stats = {
            totalLogs: 0,
            processedLogs: 0,
            errorLogs: 0,
            averageProcessingTime: 0,
            parserStats: this.stats.parserStats.map(stat => ({
                ...stat,
                stats: {
                    parseCount: 0,
                    successCount: 0,
                    errorCount: 0,
                    averageTime: 0
                }
            }))
        }

        this.cacheStats = {
            hits: 0,
            misses: 0,
            size: 0,
            maxSize: this.config.cacheConfig?.maxSize || 1000,
            hitRate: 0
        }

        this.batchProcessor.resetStats()
    }

    /**
     * 销毁管道
     */
    destroy(): void {
        try {
            this.debugLog('destroy', '开始销毁日志管道', {
                cacheSize: this.cache.size,
                parserCount: this.parsers.length,
                stats: this.stats
            })

            this.batchProcessor.destroy()
            this.cache.clear()
            this.cacheHotPath.clear()
            this.parsers.length = 0
            this.outputCallback = undefined
            LogPipeline.instance = null

            this.debugLog('destroy', '日志管道销毁完成')
        } catch (error) {
            console.error('销毁日志管道时发生错误:', error)
        }
    }

    // 错误处理增强：调试日志
    private debugLog(method: string, message: string, data?: any): void {
        if (this.config.enableFiltering) {
            console.debug(`[LogPipeline.${method}] ${message}`, data)
        }
    }

    // 错误处理增强：警告日志
    private warnLog(method: string, message: string, data?: any): void {
        console.warn(`[LogPipeline.${method}] ${message}`, data)
    }

    // 错误处理增强：错误日志
    private errorLog(method: string, message: string, data?: any): void {
        console.error(`[LogPipeline.${method}] ${message}`, data)
    }
}

/**
 * 创建默认的日志管道配置
 */
export function createDefaultPipelineConfig(): LogPipelineConfig {
    return {
        enableCache: true,
        enableBatching: true,
        enableCompression: false,
        enableFiltering: false,
        cacheConfig: {
            maxSize: 1000,
            ttl: 300000, // 5分钟
            enableLRU: true,
            enableStats: true
        },
        batchConfig: createDefaultBatchConfig(),
        transmitOptions: {
            enableCompression: false,
            enableBatching: true,
            enablePriority: true,
            retryCount: 3,
            retryDelay: 1000
        }
    }
}

/**
 * 创建高性能日志管道配置
 */
export function createHighPerformancePipelineConfig(): LogPipelineConfig {
    return {
        enableCache: true,
        enableBatching: true,
        enableCompression: true,
        enableFiltering: false,
        cacheConfig: {
            maxSize: 2000,
            ttl: 600000, // 10分钟
            enableLRU: true,
            enableStats: true
        },
        batchConfig: {
            batchSize: 200,
            batchTimeout: 500,
            maxBatchSize: 500,
            priorityLevels: ['CRITICAL', 'ERROR', 'WARN', 'INFO', 'DEBUG', 'TRACE'] as any,
            immediateLevels: ['CRITICAL', 'ERROR', 'WARN'] as any
        },
        transmitOptions: {
            enableCompression: true,
            enableBatching: true,
            enablePriority: true,
            retryCount: 5,
            retryDelay: 500
        }
    }
}