/**
 * 日志批处理器
 * 实现智能批处理功能，根据日志优先级和数量动态调整批处理策略
 */

import { ParsedLogEntry, LogLevel, LogBatchConfig, LogBatchStats } from '../types/log'

export class LogBatchProcessor {
    private config: LogBatchConfig
    private pendingLogs: ParsedLogEntry[] = []
    private priorityQueues: Map<LogLevel, ParsedLogEntry[]> = new Map()
    private batchTimer: NodeJS.Timeout | null = null
    private processingCallback?: (logs: ParsedLogEntry[]) => void
    private stats: LogBatchStats = {
        totalProcessed: 0,
        totalBatches: 0,
        averageBatchSize: 0,
        processingTime: 0,
        errorCount: 0
    }

    constructor(config: LogBatchConfig, callback?: (logs: ParsedLogEntry[]) => void) {
        this.config = config
        this.processingCallback = callback

        // 初始化优先级队列
        this.initializePriorityQueues()

        // 性能优化：预分配数组空间
        this.pendingLogs = new Array(config.maxBatchSize * 2)
        this.pendingLogs.length = 0
    }

    /**
     * 初始化优先级队列
     */
    private initializePriorityQueues(): void {
        this.config.priorityLevels.forEach(level => {
            this.priorityQueues.set(level, [])
        })
    }

    /**
     * 添加日志到批处理器
     * @param log 日志条目
     */
    addLog(log: ParsedLogEntry): void {
        if (!log) return

        const startTime = performance.now()

        try {
            // 检查是否为立即处理级别
            if (this.config.immediateLevels.includes(log.level)) {
                this.processImmediateLog(log)
                return
            }

            // 性能优化：直接使用索引而不是push
            const queue = this.priorityQueues.get(log.level)
            if (queue) {
                queue.push(log)
            } else {
                // 如果没有对应的队列，添加到待处理列表
                this.pendingLogs[this.pendingLogs.length++] = log
            }

            // 检查是否需要立即处理批次
            if (this.shouldProcessBatch()) {
                this.processBatch()
            } else {
                // 设置批处理定时器
                this.scheduleBatchProcessing()
            }

            this.stats.totalProcessed++
        } catch (error) {
            this.stats.errorCount++
            console.error('添加日志到批处理器失败:', error)
        } finally {
            this.stats.processingTime += performance.now() - startTime
        }
    }

    /**
     * 立即处理高优先级日志
     * @param log 日志条目
     */
    private processImmediateLog(log: ParsedLogEntry): void {
        if (this.processingCallback) {
            try {
                this.processingCallback([log])
                this.stats.totalBatches++
                this.stats.totalProcessed++
            } catch (error) {
                this.stats.errorCount++
                console.error('立即处理日志失败:', error)
            }
        }
    }

    /**
     * 检查是否应该处理批次
     */
    private shouldProcessBatch(): boolean {
        const totalLogs = this.getTotalPendingLogs()

        // 如果总日志数达到批次大小，立即处理
        if (totalLogs >= this.config.batchSize) {
            return true
        }

        // 如果任一优先级队列达到最大批次大小，立即处理
        for (const queue of this.priorityQueues.values()) {
            if (queue.length >= this.config.maxBatchSize) {
                return true
            }
        }

        return false
    }

    /**
     * 获取待处理日志总数
     */
    private getTotalPendingLogs(): number {
        let total = this.pendingLogs.length
        for (const queue of this.priorityQueues.values()) {
            total += queue.length
        }
        return total
    }

    /**
     * 安排批处理定时任务
     */
    private scheduleBatchProcessing(): void {
        // 如果已经有定时器在运行，不重复设置
        if (this.batchTimer) {
            return
        }

        this.batchTimer = setTimeout(() => {
            this.processBatch()
            this.batchTimer = null
        }, this.config.batchTimeout)
    }

    /**
     * 处理批次
     */
    private processBatch(): void {
        const startTime = performance.now()

        try {
            // 清除定时器
            if (this.batchTimer) {
                clearTimeout(this.batchTimer)
                this.batchTimer = null
            }

            // 按优先级收集日志
            const batchLogs = this.collectBatchLogs()

            if (batchLogs.length === 0) {
                return
            }

            // 性能优化：使用requestIdleCallback进行非关键处理
            if (this.processingCallback) {
                if (typeof requestIdleCallback !== 'undefined') {
                    requestIdleCallback(() => {
                        this.processingCallback?.(batchLogs)
                    }, { timeout: 100 })
                } else {
                    // 降级到setTimeout
                    setTimeout(() => {
                        this.processingCallback?.(batchLogs)
                    }, 0)
                }
            }

            // 更新统计信息
            this.stats.totalBatches++
            this.updateAverageBatchSize(batchLogs.length)

        } catch (error) {
            this.stats.errorCount++
            console.error('批处理日志失败:', error)
        } finally {
            this.stats.processingTime += performance.now() - startTime
        }
    }

    /**
     * 按优先级收集批次日志
     */
    private collectBatchLogs(): ParsedLogEntry[] {
        // 性能优化：预分配数组
        const batchLogs: ParsedLogEntry[] = new Array(this.config.batchSize)
        let batchIndex = 0

        // 按优先级顺序从队列中取出日志
        for (const level of this.config.priorityLevels) {
            const queue = this.priorityQueues.get(level)
            if (queue && queue.length > 0) {
                const takeCount = Math.min(queue.length, this.config.maxBatchSize, this.config.batchSize - batchIndex)
                for (let i = 0; i < takeCount && batchIndex < this.config.batchSize; i++) {
                    batchLogs[batchIndex++] = queue[i]
                }
                queue.splice(0, takeCount)
            }

            if (batchIndex >= this.config.batchSize) break
        }

        // 如果还有空间，从待处理列表中取出
        if (batchIndex < this.config.batchSize) {
            const remainingCount = Math.min(this.pendingLogs.length, this.config.batchSize - batchIndex)
            for (let i = 0; i < remainingCount; i++) {
                batchLogs[batchIndex++] = this.pendingLogs[i]
            }
            this.pendingLogs.splice(0, remainingCount)
        }

        // 调整数组大小到实际长度
        batchLogs.length = batchIndex
        return batchLogs
    }

    /**
     * 更新平均批次大小
     */
    private updateAverageBatchSize(currentBatchSize: number): void {
        if (this.stats.totalBatches === 0) {
            this.stats.averageBatchSize = currentBatchSize
        } else {
            this.stats.averageBatchSize =
                (this.stats.averageBatchSize * (this.stats.totalBatches - 1) + currentBatchSize) /
                this.stats.totalBatches
        }
    }

    /**
     * 立即刷新所有待处理的日志
     */
    flush(): void {
        this.processBatch()
    }

    /**
     * 更新配置
     * @param newConfig 新的配置
     */
    updateConfig(newConfig: Partial<LogBatchConfig>): void {
        this.config = { ...this.config, ...newConfig }

        // 如果优先级级别发生变化，重新初始化队列
        if (newConfig.priorityLevels) {
            // 保存现有日志
            const existingLogs = this.collectAllPendingLogs()

            // 重新初始化队列
            this.initializePriorityQueues()

            // 重新添加日志
            existingLogs.forEach(log => this.addLog(log))
        }
    }

    /**
     * 收集所有待处理的日志
     */
    private collectAllPendingLogs(): ParsedLogEntry[] {
        // 性能优化：计算总大小并预分配
        let totalSize = this.pendingLogs.length
        for (const queue of this.priorityQueues.values()) {
            totalSize += queue.length
        }

        const allLogs: ParsedLogEntry[] = new Array(totalSize)
        let index = 0

        // 收集优先级队列中的日志
        for (const queue of this.priorityQueues.values()) {
            for (let i = 0; i < queue.length; i++) {
                allLogs[index++] = queue[i]
            }
            queue.length = 0 // 清空队列
        }

        // 收集待处理列表中的日志
        for (let i = 0; i < this.pendingLogs.length; i++) {
            allLogs[index++] = this.pendingLogs[i]
        }
        this.pendingLogs.length = 0

        return allLogs
    }

    /**
     * 获取统计信息
     */
    getStats(): LogBatchStats {
        return { ...this.stats }
    }

    /**
     * 获取当前配置
     */
    getConfig(): LogBatchConfig {
        return { ...this.config }
    }

    /**
     * 获取待处理日志数量
     */
    getPendingCount(): number {
        return this.getTotalPendingLogs()
    }

    /**
     * 重置统计信息
     */
    resetStats(): void {
        this.stats = {
            totalProcessed: 0,
            totalBatches: 0,
            averageBatchSize: 0,
            processingTime: 0,
            errorCount: 0
        }
    }

    /**
     * 清空所有待处理的日志
     */
    clear(): void {
        // 清空所有队列
        for (const queue of this.priorityQueues.values()) {
            queue.length = 0
        }
        this.pendingLogs.length = 0

        // 清除定时器
        if (this.batchTimer) {
            clearTimeout(this.batchTimer)
            this.batchTimer = null
        }
    }

    /**
     * 销毁批处理器
     */
    destroy(): void {
        this.clear()
        this.processingCallback = undefined
        this.priorityQueues.clear()
    }
}

/**
 * 创建默认的批处理配置
 */
export function createDefaultBatchConfig(): LogBatchConfig {
    return {
        batchSize: 100,
        batchTimeout: 1000, // 1秒
        maxBatchSize: 200,
        priorityLevels: [
            LogLevel.CRITICAL,
            LogLevel.ERROR,
            LogLevel.WARN,
            LogLevel.INFO,
            LogLevel.DEBUG,
            LogLevel.TRACE
        ],
        immediateLevels: [
            LogLevel.CRITICAL,
            LogLevel.ERROR
        ]
    }
}

/**
 * 创建高性能批处理配置
 */
export function createHighPerformanceBatchConfig(): LogBatchConfig {
    return {
        batchSize: 200,
        batchTimeout: 500, // 0.5秒
        maxBatchSize: 500,
        priorityLevels: [
            LogLevel.CRITICAL,
            LogLevel.ERROR,
            LogLevel.WARN,
            LogLevel.INFO,
            LogLevel.DEBUG,
            LogLevel.TRACE
        ],
        immediateLevels: [
            LogLevel.CRITICAL,
            LogLevel.ERROR,
            LogLevel.WARN
        ]
    }
}

/**
 * 创建低延迟批处理配置
 */
export function createLowLatencyBatchConfig(): LogBatchConfig {
    return {
        batchSize: 50,
        batchTimeout: 200, // 0.2秒
        maxBatchSize: 100,
        priorityLevels: [
            LogLevel.CRITICAL,
            LogLevel.ERROR,
            LogLevel.WARN,
            LogLevel.INFO,
            LogLevel.DEBUG,
            LogLevel.TRACE
        ],
        immediateLevels: [
            LogLevel.CRITICAL,
            LogLevel.ERROR,
            LogLevel.WARN,
            LogLevel.INFO
        ]
    }
}