/**
 * Loguru后端日志解析器
 * 专门用于解析Python Loguru库生成的日志格式
 * 简化版本，使用直接有效的解析方法
 */

import { ParsedLogEntry, ILogParser, LogLevel, LogSource } from '../types/log'

/**
 * 简单而有效的日志解析函数
 * 直接解析日志行，提取时间戳、级别、模块和消息
 */
function parseLoguruLogLine(line: string): ParsedLogEntry | null {
    // 移除ANSI颜色代码
    const cleanLine = line.replace(/\x1b\[[0-9;]*m/g, '');

    // 使用简单的正则表达式匹配
    // 格式: 时间戳 | 级别 | 模块 | 消息
    const match = cleanLine.match(/^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3})\s+\|\s*(\w+)\s+\|\s*([^|]+?)\s*\|\s*(.+)$/);

    if (match) {
        const timestamp = new Date(match[1]);
        const level = normalizeLogLevel(match[2]);
        const module = match[3].trim();
        const message = match[4].trim();

        return {
            timestamp,
            level,
            module,
            message,
            source: LogSource.BACKEND,
            originalLog: line,
            isValid: true
        };
    }

    return null;
}

/**
 * 标准化日志级别
 */
function normalizeLogLevel(level: string): LogLevel {
    const normalizedLevel = level.toUpperCase().trim();

    switch (normalizedLevel) {
        case 'TRACE':
            return LogLevel.TRACE;
        case 'DEBUG':
            return LogLevel.DEBUG;
        case 'INFO':
        case 'SUCCESS':
            return LogLevel.INFO;
        case 'WARN':
        case 'WARNING':
            return LogLevel.WARN;
        case 'ERROR':
        case 'CRITICAL':
        case 'FATAL':
            return LogLevel.ERROR;
        default:
            return LogLevel.INFO;
    }
}

/**
 * Loguru后端日志解析器
 * 实现ILogParser接口，专门解析Loguru格式的日志
 */
export class LoguruBackendLogParser implements ILogParser {
    private static instance: LoguruBackendLogParser
    private cache: Map<string, ParsedLogEntry> = new Map()
    private cacheEnabled: boolean = true
    private maxCacheSize: number = 1000
    private stats = {
        parseCount: 0,
        successCount: 0,
        errorCount: 0,
        averageTime: 0,
        cacheHits: 0,
        cacheMisses: 0
    }

    private constructor() { }

    /**
     * 获取单例实例
     */
    static getInstance(): LoguruBackendLogParser {
        if (!LoguruBackendLogParser.instance) {
            LoguruBackendLogParser.instance = new LoguruBackendLogParser()
        }
        return LoguruBackendLogParser.instance
    }

    /**
     * 启用/禁用缓存
     */
    setCacheEnabled(enabled: boolean): void {
        this.cacheEnabled = enabled
        if (!enabled) {
            this.cache.clear()
        }
    }

    /**
     * 设置最大缓存大小
     */
    setMaxCacheSize(size: number): void {
        this.maxCacheSize = size
        this.enforceCacheSize()
    }

    /**
     * 强制执行缓存大小限制（LRU策略）
     */
    private enforceCacheSize(): void {
        if (this.cache.size > this.maxCacheSize) {
            const keysToDelete = Array.from(this.cache.keys()).slice(0, this.cache.size - this.maxCacheSize)
            keysToDelete.forEach(key => this.cache.delete(key))
        }
    }

    /**
     * 生成缓存键
     */
    private generateCacheKey(logLine: string): string {
        // 使用简单的哈希函数
        let hash = 0
        for (let i = 0; i < logLine.length; i++) {
            const char = logLine.charCodeAt(i)
            hash = ((hash << 5) - hash) + char
            hash = hash & hash // 转换为32位整数
        }
        return Math.abs(hash).toString(36)
    }

    /**
     * 检查是否能解析指定格式的日志
     */
    canParse(logLine: string): boolean {
        if (!logLine || logLine.trim() === '') {
            return false
        }

        const trimmedLog = logLine.trim()
        const cleanLine = trimmedLog.replace(/\x1b\[[0-9;]*m/g, '');

        // 使用简单的正则表达式检查
        const match = cleanLine.match(/^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3})\s+\|\s*(\w+)\s+\|\s*([^|]+?)\s*\|\s*(.+)$/);
        return match !== null;
    }

    /**
     * 解析日志行
     */
    parse(logLine: string): ParsedLogEntry {
        const startTime = Date.now()
        this.stats.parseCount++


        // 检查缓存
        if (this.cacheEnabled) {
            const cacheKey = this.generateCacheKey(logLine)
            const cached = this.cache.get(cacheKey)
            if (cached) {
                this.stats.cacheHits++
                return cached
            }
            this.stats.cacheMisses++
        }

        let result: ParsedLogEntry

        try {
            // 使用简化的解析函数
            const parseResult = parseLoguruLogLine(logLine)

            if (parseResult) {
                result = parseResult
            } else {
                // 如果简单解析失败，使用降级解析
                result = this.fallbackParse(logLine)
            }

            this.stats.successCount++

        } catch (error) {
            result = {
                timestamp: new Date(),
                level: LogLevel.ERROR,
                module: 'LoguruParser',
                message: `解析失败: ${error instanceof Error ? error.message : String(error)}`,
                source: LogSource.SYSTEM,
                originalLog: logLine,
                isValid: false,
                parseError: error instanceof Error ? error.message : String(error)
            }
            this.stats.errorCount++

        }

        // 更新缓存
        if (this.cacheEnabled && result.isValid) {
            const cacheKey = this.generateCacheKey(logLine)
            this.cache.set(cacheKey, result)
            this.enforceCacheSize()
        }

        // 更新平均解析时间
        const processingTime = Date.now() - startTime
        this.updateAverageTime(processingTime)

        return result
    }

    /**
     * 错误恢复策略：当解析失败时的降级处理
     */
    private fallbackParse(logLine: string): ParsedLogEntry {
        const trimmedLog = logLine.trim()


        // 尝试使用更灵活的正则表达式解析
        // 格式: 时间戳 | 级别 | 模块 | 消息
        const flexiblePattern = /^(\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d{3})?)\s*\|\s*(\w+)\s*\|\s*([^|]+?)\s*\|\s*(.+)$/i
        const match = trimmedLog.match(flexiblePattern)

        if (match) {
            const timestamp = new Date(match[1].replace('T', ' '))
            const level = normalizeLogLevel(match[2])
            const module = match[3].trim()
            const message = match[4].trim()


            return {
                timestamp,
                level,
                module,
                message,
                source: LogSource.BACKEND,
                originalLog: logLine,
                isValid: true,
                parseError: '使用降级解析策略'
            }
        }

        // 如果还是失败，尝试提取时间戳和级别
        const timestampRegex = /(\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d{3})?)/
        const timestampMatch = trimmedLog.match(timestampRegex)
        const timestamp = timestampMatch ? new Date(timestampMatch[1].replace('T', ' ')) : new Date()

        // 尝试提取日志级别
        const levelRegex = /\b(TRACE|DEBUG|INFO|WARN|ERROR|CRITICAL|FATAL|SUCCESS)\b/i
        const levelMatch = trimmedLog.match(levelRegex)
        const level = levelMatch ? normalizeLogLevel(levelMatch[1]) : LogLevel.INFO

        // 尝试提取模块（在级别和消息之间）
        const moduleRegex = new RegExp(`\\b(TRACE|DEBUG|INFO|WARN|ERROR|CRITICAL|FATAL|SUCCESS)\\b\\s*\\|\\s*([^|]+?)\\s*\\|`, 'i')
        const moduleMatch = trimmedLog.match(moduleRegex)
        let module = moduleMatch ? moduleMatch[2].trim() : 'Unknown'

        // 如果还是无法提取模块，尝试更简单的方法
        if (module === 'Unknown') {
            const parts = trimmedLog.split('|')
            if (parts.length >= 3) {
                const potentialModule = parts[2].trim()
                if (potentialModule && potentialModule !== '') {
                    module = potentialModule
                }
            }
        }

        // 提取纯消息内容（移除时间戳和级别）
        let message = trimmedLog
        if (timestampMatch) {
            message = message.replace(timestampMatch[1], '').replace(/^\s*\|\s*/, '')
        }
        if (levelMatch) {
            message = message.replace(new RegExp(`\\b${levelMatch[1]}\\b`, 'i'), '').replace(/^\s*\|\s*/, '')
        }
        if (moduleMatch) {
            message = message.replace(moduleMatch[0], '').replace(/^\s*\|\s*/, '')
        }
        message = message.trim()


        return {
            timestamp,
            level,
            module,
            message,
            source: LogSource.BACKEND,
            originalLog: logLine,
            isValid: true,
            parseError: '使用降级解析策略'
        }
    }

    /**
     * 更新平均解析时间
     */
    private updateAverageTime(time: number): void {
        if (this.stats.parseCount === 0) {
            this.stats.averageTime = time
        } else {
            this.stats.averageTime =
                (this.stats.averageTime * (this.stats.parseCount - 1) + time) /
                this.stats.parseCount
        }
    }

    /**
     * 获取解析器名称
     */
    getFormatName(): string {
        return 'LoguruBackendLogParser'
    }

    /**
     * 获取解析器优先级
     */
    getPriority(): number {
        return 200 // 高优先级，专门用于Loguru格式
    }

    /**
     * 获取统计信息
     */
    getStats() {
        return { ...this.stats }
    }

    /**
     * 重置统计信息
     */
    resetStats(): void {
        this.stats = {
            parseCount: 0,
            successCount: 0,
            errorCount: 0,
            averageTime: 0,
            cacheHits: 0,
            cacheMisses: 0
        }
    }

    /**
     * 清空缓存
     */
    clearCache(): void {
        this.cache.clear()
    }

    /**
     * 获取缓存大小
     */
    getCacheSize(): number {
        return this.cache.size
    }

    /**
     * 获取缓存命中率
     */
    getCacheHitRate(): number {
        const total = this.stats.cacheHits + this.stats.cacheMisses
        return total > 0 ? this.stats.cacheHits / total : 0
    }

    /**
     * 将解析结果转换为前端LogEntry格式
     */
    toLogEntry(parsedLog: ParsedLogEntry): ParsedLogEntry {
        return parsedLog
    }

    /**
     * 直接解析并返回前端日志条目
     */
    parseToLogEntry(logLine: string): ParsedLogEntry {
        return this.parse(logLine)
    }
}

// 导出单例实例
export const loguruBackendLogParser = LoguruBackendLogParser.getInstance()

// 导出简单解析函数，供测试使用
export { parseLoguruLogLine }