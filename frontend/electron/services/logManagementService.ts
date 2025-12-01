/**
 * 日志管理服务
 * 实现日志的统一管理，支持日志订阅、过滤和分发
 * 集成批处理和缓存机制
 */

import { EventEmitter } from 'events'
import {
    ParsedLogEntry,
    LogLevel,
    LogSource,
    ILogFilter,
    LogFilterConditions,
    LogPipelineConfig,
    LogProcessResult,
    LogProcessingStats
} from '../types/log'
import { LogPipeline } from '../utils/logPipeline'
import { GenericLogParser } from '../utils/genericLogParser'
import { LogFormatter } from '../utils/logFormatter'

// 日志订阅者接口
export interface ILogSubscriber {
    id: string
    callback: (logs: ParsedLogEntry[]) => void
    filter?: ILogFilter
    enabled: boolean
}

// 日志管理配置
export interface LogManagementConfig {
    maxMemoryLogs: number
    enablePersistence: boolean
    persistencePath?: string
    pipelineConfig?: LogPipelineConfig
    enableRealTimeProcessing: boolean
    bufferSize: number
    flushInterval: number
}

// 日志统计信息
export interface LogManagementStats extends LogProcessingStats {
    subscribersCount: number
    memoryUsage: number
    lastLogTime?: Date
    totalReceived: number
    totalFiltered: number
    totalDistributed: number
}

// 默认配置
const DEFAULT_CONFIG: LogManagementConfig = {
    maxMemoryLogs: 10000,
    enablePersistence: true,
    enableRealTimeProcessing: true,
    bufferSize: 100,
    flushInterval: 1000
}

export class LogManagementService extends EventEmitter {
    private static instance: LogManagementService | null = null
    private config: LogManagementConfig
    private pipeline: LogPipeline
    private subscribers: Map<string, ILogSubscriber> = new Map()
    private memoryLogs: ParsedLogEntry[] = []
    private isInitialized = false
    private processingTimer: NodeJS.Timeout | null = null
    private stats: LogManagementStats = {
        totalLogs: 0,
        processedLogs: 0,
        errorLogs: 0,
        averageProcessingTime: 0,
        parserStats: [],
        subscribersCount: 0,
        memoryUsage: 0,
        totalReceived: 0,
        totalFiltered: 0,
        totalDistributed: 0
    }

    private constructor(config?: Partial<LogManagementConfig>) {
        super()

        this.config = { ...DEFAULT_CONFIG, ...config }

        // 初始化日志管道
        this.pipeline = LogPipeline.getInstance(this.config.pipelineConfig)

        // 设置管道输出回调
        this.pipeline.setOutputCallback(this.handlePipelineOutput.bind(this))

        // 注册默认解析器
        this.registerDefaultParsers()
    }

    /**
     * 获取单例实例
     */
    static getInstance(config?: Partial<LogManagementConfig>): LogManagementService {
        if (!LogManagementService.instance) {
            LogManagementService.instance = new LogManagementService(config)
        }
        return LogManagementService.instance
    }

    /**
     * 初始化服务
     */
    async initialize(): Promise<void> {
        if (this.isInitialized) {
            return
        }

        try {
            // 启动实时处理
            if (this.config.enableRealTimeProcessing) {
                this.startRealTimeProcessing()
            }

            // 加载持久化日志（如果启用）
            if (this.config.enablePersistence && this.config.persistencePath) {
                await this.loadPersistedLogs()
            }

            this.isInitialized = true
            this.emit('initialized')
        } catch (error) {
            this.emit('error', error)
            throw error
        }
    }

    /**
     * 注册默认解析器
     */
    private registerDefaultParsers(): void {
        this.pipeline.registerParser(new GenericLogParser())
    }

    /**
     * 启动实时处理
     */
    private startRealTimeProcessing(): void {
        if (this.processingTimer) {
            clearInterval(this.processingTimer)
        }

        this.processingTimer = setInterval(() => {
            this.flushBuffer()
        }, this.config.flushInterval)
    }

    /**
     * 停止实时处理
     */
    private stopRealTimeProcessing(): void {
        if (this.processingTimer) {
            clearInterval(this.processingTimer)
            this.processingTimer = null
        }
    }

    /**
     * 处理原始日志
     */
    async processLog(rawLog: string, source: LogSource = LogSource.SYSTEM): Promise<LogProcessResult> {
        this.stats.totalReceived++

        try {
            const result = await this.pipeline.processLog(rawLog, source)

            if (result.success) {
                this.stats.processedLogs++
            } else {
                this.stats.errorLogs++
            }

            return result
        } catch (error) {
            this.stats.errorLogs++
            this.emit('error', error)

            return {
                success: false,
                processedCount: 0,
                errorCount: 1,
                errors: [String(error)],
                processingTime: 0
            }
        }
    }

    /**
     * 批量处理日志
     */
    async processBatchLogs(rawLogs: string[], source: LogSource = LogSource.SYSTEM): Promise<LogProcessResult> {
        const results: LogProcessResult[] = []

        for (const rawLog of rawLogs) {
            const result = await this.processLog(rawLog, source)
            results.push(result)
        }

        // 合并结果
        return results.reduce((acc, result) => ({
            success: acc.success && result.success,
            processedCount: acc.processedCount + result.processedCount,
            errorCount: acc.errorCount + result.errorCount,
            errors: [...acc.errors, ...result.errors],
            processingTime: acc.processingTime + result.processingTime
        }), {
            success: true,
            processedCount: 0,
            errorCount: 0,
            errors: [],
            processingTime: 0
        })
    }

    /**
     * 处理管道输出
     */
    private handlePipelineOutput(formattedLog: string): void {
        // 这里可以处理格式化后的日志，例如发送到文件或其他系统
        this.emit('formatted-log', formattedLog)
    }

    /**
     * 添加日志到内存
     */
    private addLogToMemory(log: ParsedLogEntry): void {
        this.memoryLogs.push(log)

        // 限制内存中的日志数量
        if (this.memoryLogs.length > this.config.maxMemoryLogs) {
            this.memoryLogs = this.memoryLogs.slice(-this.config.maxMemoryLogs)
        }

        // 更新统计信息
        this.stats.memoryUsage = this.memoryLogs.length
        this.stats.lastLogTime = log.timestamp

        // 触发日志事件
        this.emit('log-added', log)

        // 分发给订阅者
        this.distributeToSubscribers([log])
    }

    /**
     * 刷新缓冲区
     */
    private flushBuffer(): void {
        this.pipeline.flush()
    }

    /**
     * 订阅日志
     */
    subscribe(
        id: string,
        callback: (logs: ParsedLogEntry[]) => void,
        filter?: ILogFilter
    ): void {
        const subscriber: ILogSubscriber = {
            id,
            callback,
            filter,
            enabled: true
        }

        this.subscribers.set(id, subscriber)
        this.stats.subscribersCount = this.subscribers.size

        // 立即发送现有日志
        if (this.memoryLogs.length > 0) {
            const filteredLogs = filter ? filter.apply(this.memoryLogs) : this.memoryLogs
            if (filteredLogs.length > 0) {
                callback(filteredLogs)
            }
        }

        this.emit('subscriber-added', id)
    }

    /**
     * 取消订阅
     */
    unsubscribe(id: string): void {
        if (this.subscribers.has(id)) {
            this.subscribers.delete(id)
            this.stats.subscribersCount = this.subscribers.size
            this.emit('subscriber-removed', id)
        }
    }

    /**
     * 启用/禁用订阅者
     */
    toggleSubscriber(id: string, enabled: boolean): void {
        const subscriber = this.subscribers.get(id)
        if (subscriber) {
            subscriber.enabled = enabled
            this.emit('subscriber-toggled', { id, enabled })
        }
    }

    /**
     * 分发日志给订阅者
     */
    private distributeToSubscribers(logs: ParsedLogEntry[]): void {
        if (logs.length === 0) {
            return
        }

        let distributedCount = 0

        for (const subscriber of this.subscribers.values()) {
            if (!subscriber.enabled) {
                continue
            }

            try {
                let filteredLogs = logs

                // 应用过滤器
                if (subscriber.filter) {
                    filteredLogs = subscriber.filter.apply(logs)
                }

                if (filteredLogs.length > 0) {
                    subscriber.callback(filteredLogs)
                    distributedCount += filteredLogs.length
                }
            } catch (error) {
                this.emit('error', new Error(`订阅者 ${subscriber.id} 处理失败: ${error}`))
            }
        }

        this.stats.totalDistributed += distributedCount
    }

    /**
     * 获取日志
     */
    getLogs(
        conditions?: LogFilterConditions,
        limit?: number,
        offset?: number
    ): ParsedLogEntry[] {
        let logs = [...this.memoryLogs]

        // 应用过滤条件
        if (conditions) {
            logs = this.applyFilterConditions(logs, conditions)
        }

        // 排序（最新的在前）
        logs.sort((a, b) => b.timestamp.getTime() - a.timestamp.getTime())

        // 应用分页
        if (offset && offset > 0) {
            logs = logs.slice(offset)
        }

        if (limit && limit > 0) {
            logs = logs.slice(0, limit)
        }

        return logs
    }

    /**
     * 应用过滤条件
     */
    private applyFilterConditions(logs: ParsedLogEntry[], conditions: LogFilterConditions): ParsedLogEntry[] {
        return logs.filter(log => {
            // 级别过滤
            if (conditions.levels && conditions.levels.length > 0) {
                if (!conditions.levels.includes(log.level)) {
                    return false
                }
            }

            // 模块过滤
            if (conditions.modules && conditions.modules.length > 0) {
                if (!conditions.modules.some(module => log.module.includes(module))) {
                    return false
                }
            }

            // 时间范围过滤
            if (conditions.timeRange) {
                const [startTime, endTime] = conditions.timeRange
                if (log.timestamp < startTime || log.timestamp > endTime) {
                    return false
                }
            }

            // 关键词过滤
            if (conditions.keywords && conditions.keywords.length > 0) {
                const searchText = (log.message + ' ' + log.module).toLowerCase()
                if (!conditions.keywords.some(keyword =>
                    searchText.includes(keyword.toLowerCase())
                )) {
                    return false
                }
            }

            // 来源过滤
            if (conditions.sources && conditions.sources.length > 0) {
                if (!log.source || !conditions.sources.includes(log.source)) {
                    return false
                }
            }

            return true
        })
    }

    /**
     * 清空日志
     */
    clearLogs(): void {
        this.memoryLogs = []
        this.stats.memoryUsage = 0
        this.stats.lastLogTime = undefined
        this.emit('logs-cleared')
    }

    /**
     * 导出日志
     */
    async exportLogs(
        conditions?: LogFilterConditions,
        format: 'json' | 'csv' | 'txt' = 'json'
    ): Promise<string> {
        const logs = this.getLogs(conditions)

        switch (format) {
            case 'json':
                return JSON.stringify(logs, null, 2)

            case 'csv':
                const headers = ['timestamp', 'level', 'module', 'source', 'message']
                const csvRows = [
                    headers.join(','),
                    ...logs.map(log => [
                        log.timestamp.toISOString(),
                        log.level,
                        log.module,
                        log.source,
                        `"${log.message.replace(/"/g, '""')}"`
                    ].join(','))
                ]
                return csvRows.join('\n')

            case 'txt':
                return LogFormatter.formatBatch(logs, { includeColors: false }).join('\n')

            default:
                throw new Error(`不支持的导出格式: ${format}`)
        }
    }

    /**
     * 加载持久化日志
     */
    private async loadPersistedLogs(): Promise<void> {
        // 这里可以实现从文件加载日志的逻辑
        // 暂时留空，可以根据需要实现
    }

    /**
     * 持久化日志
     */
    private async persistLogs(): Promise<void> {
        // 这里可以实现保存日志到文件的逻辑
        // 暂时留空，可以根据需要实现
    }

    /**
     * 获取统计信息
     */
    getStats(): LogManagementStats {
        // 更新管道统计信息
        const pipelineStats = this.pipeline.getStats()

        return {
            ...this.stats,
            ...pipelineStats
        }
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
            parserStats: [],
            subscribersCount: this.subscribers.size,
            memoryUsage: this.memoryLogs.length,
            totalReceived: 0,
            totalFiltered: 0,
            totalDistributed: 0
        }

        this.pipeline.resetStats()
    }

    /**
     * 更新配置
     */
    updateConfig(newConfig: Partial<LogManagementConfig>): void {
        this.config = { ...this.config, ...newConfig }

        // 更新管道配置
        if (newConfig.pipelineConfig) {
            this.pipeline.updateConfig(newConfig.pipelineConfig)
        }

        // 重启实时处理（如果需要）
        if (newConfig.enableRealTimeProcessing !== undefined) {
            if (newConfig.enableRealTimeProcessing) {
                this.startRealTimeProcessing()
            } else {
                this.stopRealTimeProcessing()
            }
        }

        this.emit('config-updated', this.config)
    }

    /**
     * 获取配置
     */
    getConfig(): LogManagementConfig {
        return { ...this.config }
    }

    /**
     * 获取订阅者列表
     */
    getSubscribers(): ILogSubscriber[] {
        return Array.from(this.subscribers.values())
    }

    /**
     * 销毁服务
     */
    async destroy(): Promise<void> {
        // 停止实时处理
        this.stopRealTimeProcessing()

        // 刷新缓冲区
        this.flushBuffer()

        // 持久化日志
        if (this.config.enablePersistence) {
            await this.persistLogs()
        }

        // 清理资源
        this.subscribers.clear()
        this.memoryLogs = []
        this.pipeline.destroy()

        // 移除所有监听器
        this.removeAllListeners()

        this.isInitialized = false
        LogManagementService.instance = null

        this.emit('destroyed')
    }

    /**
     * 处理ParsedLogEntry（用于内部使用）
     */
    handleParsedLogEntry(log: ParsedLogEntry): void {
        this.addLogToMemory(log)
    }
}

// 导出单例实例
export const logManagementService = LogManagementService.getInstance()

// 导出便捷函数
export const initializeLogManagement = async (config?: Partial<LogManagementConfig>) => {
    await logManagementService.initialize()
    return logManagementService
}

export const processLog = async (rawLog: string, source?: LogSource) => {
    return await logManagementService.processLog(rawLog, source)
}

export const subscribeToLogs = (
    id: string,
    callback: (logs: ParsedLogEntry[]) => void,
    filter?: ILogFilter
) => {
    logManagementService.subscribe(id, callback, filter)
}

export const unsubscribeFromLogs = (id: string) => {
    logManagementService.unsubscribe(id)
}

export const getLogStats = () => {
    return logManagementService.getStats()
}