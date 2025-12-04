/**
 * 日志流处理器
 * 用于实时日志处理
 * 集成LoguruBackendLogParser进行日志解析
 * 实现背压处理机制防止内存溢出
 * 提供批量处理和异步处理能力
 * 添加错误处理和恢复机制
 */

import { ParsedLogEntry, LogLevel } from '../types/log'
import { LoguruBackendLogParser } from './loguruBackendLogParser'
import { BackendLogPrinter } from './backendLogPrinter'
import { FrontendLogAdapter } from './frontendLogAdapter'

export interface LogStreamProcessorOptions {
    batchSize?: number
    batchTimeout?: number
    maxQueueSize?: number
    enableBackpressure?: boolean
    backpressureThreshold?: number
    enablePriority?: boolean
    priorityLevels?: LogLevel[]
    enableAsync?: boolean
    maxConcurrency?: number
    enableErrorRecovery?: boolean
    maxRetryAttempts?: number
}

export interface LogStreamStats {
    totalProcessed: number
    totalErrors: number
    totalBatches: number
    averageBatchSize: number
    currentQueueSize: number
    maxQueueSizeReached: number
    backpressureEvents: number
    processingTime: number
    parserStats: any
}

export type ProcessedLogCallback = (logEntry: ParsedLogEntry) => void
export type BatchProcessedCallback = (batch: ParsedLogEntry[]) => void
export type ErrorCallback = (error: Error, logLine?: string) => void

/**
 * 日志流处理器类
 */
export class LogStreamProcessor {
    private options: Required<LogStreamProcessorOptions>
    private parser: LoguruBackendLogParser
    private backendLogPrinter: BackendLogPrinter
    private frontendLogAdapter: FrontendLogAdapter
    private processingQueue: Array<{ line: string; source: string; timestamp: number }> = []
    private isProcessing: boolean = false
    private batchTimer?: NodeJS.Timeout
    private processingPromises: Set<Promise<void>> = new Set()
    private stats: LogStreamStats
    private printerEnabled: boolean = true

    // 回调函数
    private onProcessedLog?: ProcessedLogCallback
    private onBatchProcessed?: BatchProcessedCallback
    private onError?: ErrorCallback

    constructor(options: LogStreamProcessorOptions = {}) {
        this.options = {
            batchSize: options.batchSize || 100,
            batchTimeout: options.batchTimeout || 500,
            maxQueueSize: options.maxQueueSize || 10000,
            enableBackpressure: options.enableBackpressure ?? true,
            backpressureThreshold: options.backpressureThreshold || 0.8,
            enablePriority: options.enablePriority ?? true,
            priorityLevels: options.priorityLevels || [LogLevel.ERROR, LogLevel.CRITICAL],
            enableAsync: options.enableAsync ?? true,
            maxConcurrency: options.maxConcurrency || 5,
            enableErrorRecovery: options.enableErrorRecovery ?? true,
            maxRetryAttempts: options.maxRetryAttempts || 3
        }

        this.parser = LoguruBackendLogParser.getInstance()
        this.backendLogPrinter = BackendLogPrinter.getInstance()
        this.frontendLogAdapter = FrontendLogAdapter.getInstance()

        this.stats = {
            totalProcessed: 0,
            totalErrors: 0,
            totalBatches: 0,
            averageBatchSize: 0,
            currentQueueSize: 0,
            maxQueueSizeReached: 0,
            backpressureEvents: 0,
            processingTime: 0,
            parserStats: {}
        }

        // 启动批处理定时器
        this.setupBatchTimer()

        // 初始化前端适配器
        this.initializeFrontendAdapter()
    }

    /**
     * 设置批处理定时器
     */
    private setupBatchTimer(): void {
        if (this.batchTimer) {
            clearInterval(this.batchTimer)
        }

        this.batchTimer = setInterval(() => {
            if (this.processingQueue.length > 0) {
                this.processBatch()
            }
        }, this.options.batchTimeout)
    }

    /**
     * 添加日志行到处理队列
     */
    addLogLine(line: string, source: string = 'unknown'): void {
        // 检查背压
        if (this.options.enableBackpressure && this.isBackpressureActive()) {
            this.handleBackpressure(line, source)
            return
        }

        // 检查队列大小
        if (this.processingQueue.length >= this.options.maxQueueSize) {
            this.handleQueueOverflow(line, source)
            return
        }

        // 添加到队列
        const logItem = {
            line: line.trim(),
            source,
            timestamp: Date.now()
        }

        // 优先级处理
        if (this.options.enablePriority && this.isHighPriorityLog(logItem.line)) {
            this.processingQueue.unshift(logItem) // 高优先级日志插入队列前端
        } else {
            this.processingQueue.push(logItem)
        }

        // 更新统计信息
        this.updateQueueStats()

        // 如果是高优先级日志或队列已满，立即处理
        if (this.options.enablePriority && this.isHighPriorityLog(logItem.line)) {
            this.processHighPriorityLog(logItem)
        } else if (this.processingQueue.length >= this.options.batchSize) {
            this.processBatch()
        }
    }

    /**
     * 检查是否处于背压状态
     */
    private isBackpressureActive(): boolean {
        const threshold = this.options.maxQueueSize * this.options.backpressureThreshold
        return this.processingQueue.length > threshold
    }

    /**
     * 处理背压
     */
    private handleBackpressure(line: string, source: string): void {
        this.stats.backpressureEvents++

        // 丢弃低优先级日志
        if (!this.isHighPriorityLog(line)) {
            console.warn('背压激活，丢弃低优先级日志:', line.substring(0, 100))
            return
        }

        // 强制处理高优先级日志
        this.processLogLineImmediately(line, source)
    }

    /**
     * 处理队列溢出
     */
    private handleQueueOverflow(line: string, source: string): void {
        console.warn('处理队列溢出，丢弃最旧的日志')

        // 移除最旧的日志
        this.processingQueue.shift()

        // 添加新日志
        this.addLogLine(line, source)
    }

    /**
     * 检查是否为高优先级日志
     */
    private isHighPriorityLog(line: string): boolean {
        if (!this.options.enablePriority) return false

        // 快速检查是否包含高优先级级别关键词
        return this.options.priorityLevels.some(level =>
            line.toUpperCase().includes(level.toUpperCase())
        )
    }

    /**
     * 立即处理高优先级日志
     */
    private processHighPriorityLog(logItem: { line: string; source: string; timestamp: number }): void {
        if (this.options.enableAsync) {
            const promise = this.processLogItemAsync(logItem)
            this.processingPromises.add(promise)
            promise.finally(() => {
                this.processingPromises.delete(promise)
            })
        } else {
            this.processLogItemSync(logItem)
        }
    }

    /**
     * 立即处理日志行
     */
    private processLogLineImmediately(line: string, source: string): void {
        const logItem = { line, source, timestamp: Date.now() }
        this.processLogItemSync(logItem)
    }

    /**
     * 处理批次
     */
    private async processBatch(): Promise<void> {
        if (this.isProcessing || this.processingQueue.length === 0) {
            return
        }

        this.isProcessing = true
        const startTime = Date.now()

        try {
            // 取出一批日志
            const batch = this.processingQueue.splice(0, this.options.batchSize)

            // 更新统计信息
            this.stats.totalBatches++
            this.updateAverageBatchSize(batch.length)

            if (this.options.enableAsync) {
                await this.processBatchAsync(batch)
            } else {
                this.processBatchSync(batch)
            }

        } catch (error) {
            this.handleError(error instanceof Error ? error : new Error(String(error)))
        } finally {
            this.isProcessing = false
            this.stats.processingTime += Date.now() - startTime
            this.updateQueueStats()
        }
    }

    /**
     * 异步处理批次
     */
    private async processBatchAsync(batch: Array<{ line: string; source: string; timestamp: number }>): Promise<void> {
        const promises = batch.map(logItem => this.processLogItemAsync(logItem))

        // 限制并发数
        const chunks = this.chunkArray(promises, this.options.maxConcurrency)

        for (const chunk of chunks) {
            await Promise.allSettled(chunk)
        }
    }

    /**
     * 同步处理批次
     */
    private processBatchSync(batch: Array<{ line: string; source: string; timestamp: number }>): void {
        const processedLogs: ParsedLogEntry[] = []

        for (const logItem of batch) {
            try {
                const parsedLog = this.parseLogWithRetrySync(logItem.line)
                processedLogs.push(parsedLog)


                // 简化数据传递逻辑，直接调用前端适配器
                if (this.printerEnabled && parsedLog.isValid) {
                    // 直接调用print方法，确保使用正确的日志级别和模块信息
                    this.frontendLogAdapter.print(
                        parsedLog.level,
                        parsedLog.module,
                        parsedLog.message,
                        parsedLog.source,
                        parsedLog.metadata
                    )
                }

                // 调用原有回调
                this.onProcessedLog?.(parsedLog)
            } catch (error) {
                this.handleError(error instanceof Error ? error : new Error(String(error)), logItem.line)
            }
        }

        // 触发批处理完成回调
        if (processedLogs.length > 0) {
            this.onBatchProcessed?.(processedLogs)
        }
    }

    /**
     * 异步处理单个日志项
     */
    private async processLogItemAsync(logItem: { line: string; source: string; timestamp: number }): Promise<void> {
        try {
            const parsedLog = await this.parseLogWithRetry(logItem.line)
            this.stats.totalProcessed++


            // 简化数据传递逻辑，直接调用前端适配器
            if (this.printerEnabled && parsedLog.isValid) {
                // 直接调用print方法，确保使用正确的日志级别和模块信息
                await this.frontendLogAdapter.print(
                    parsedLog.level,
                    parsedLog.module,
                    parsedLog.message,
                    parsedLog.source,
                    parsedLog.metadata
                )
            }

            // 调用原有回调
            this.onProcessedLog?.(parsedLog)
        } catch (error) {
            this.handleError(error instanceof Error ? error : new Error(String(error)), logItem.line)
        }
    }

    /**
     * 同步处理单个日志项
     */
    private processLogItemSync(logItem: { line: string; source: string; timestamp: number }): ParsedLogEntry {
        try {
            const parsedLog = this.parseLogWithRetrySync(logItem.line)
            this.stats.totalProcessed++


            // 简化数据传递逻辑，直接调用前端适配器
            if (this.printerEnabled && parsedLog.isValid) {

                // 直接调用print方法，确保使用正确的日志级别和模块信息
                this.frontendLogAdapter.print(
                    parsedLog.level,
                    parsedLog.module,
                    parsedLog.message,
                    parsedLog.source,
                    parsedLog.metadata
                )
            }

            // 调用原有回调
            this.onProcessedLog?.(parsedLog)
            return parsedLog
        } catch (error) {
            this.handleError(error instanceof Error ? error : new Error(String(error)), logItem.line)
            throw error
        }
    }

    /**
     * 带重试的日志解析（异步）
     */
    private async parseLogWithRetry(line: string, attempt: number = 1): Promise<ParsedLogEntry> {
        try {
            return this.parser.parse(line)
        } catch (error) {
            if (this.options.enableErrorRecovery && attempt < this.options.maxRetryAttempts) {
                await new Promise(resolve => setTimeout(resolve, 100 * attempt)) // 指数退避
                return this.parseLogWithRetry(line, attempt + 1)
            }
            throw error
        }
    }

    /**
     * 带重试的日志解析（同步）
     */
    private parseLogWithRetrySync(line: string, attempt: number = 1): ParsedLogEntry {
        try {
            return this.parser.parse(line)
        } catch (error) {
            if (this.options.enableErrorRecovery && attempt < this.options.maxRetryAttempts) {
                // 同步模式下简单重试
                return this.parseLogWithRetrySync(line, attempt + 1)
            }
            throw error
        }
    }

    /**
     * 处理错误
     */
    private handleError(error: Error, logLine?: string): void {
        this.stats.totalErrors++
        this.onError?.(error, logLine)
    }

    /**
     * 更新队列统计信息
     */
    private updateQueueStats(): void {
        this.stats.currentQueueSize = this.processingQueue.length

        if (this.stats.currentQueueSize > this.stats.maxQueueSizeReached) {
            this.stats.maxQueueSizeReached = this.stats.currentQueueSize
        }
    }

    /**
     * 更新平均批次大小
     */
    private updateAverageBatchSize(batchSize: number): void {
        if (this.stats.totalBatches === 1) {
            this.stats.averageBatchSize = batchSize
        } else {
            this.stats.averageBatchSize =
                (this.stats.averageBatchSize * (this.stats.totalBatches - 1) + batchSize) /
                this.stats.totalBatches
        }
    }

    /**
     * 分割数组
     */
    private chunkArray<T>(array: T[], chunkSize: number): T[][] {
        const chunks: T[][] = []
        for (let i = 0; i < array.length; i += chunkSize) {
            chunks.push(array.slice(i, i + chunkSize))
        }
        return chunks
    }

    /**
     * 设置处理后的日志回调
     */
    setProcessedLogCallback(callback: ProcessedLogCallback): void {
        this.onProcessedLog = callback
    }

    /**
     * 设置批处理完成回调
     */
    setBatchProcessedCallback(callback: BatchProcessedCallback): void {
        this.onBatchProcessed = callback
    }

    /**
     * 设置错误回调
     */
    setErrorCallback(callback: ErrorCallback): void {
        this.onError = callback
    }

    /**
     * 获取统计信息
     */
    getStats(): LogStreamStats {
        return {
            ...this.stats,
            parserStats: this.parser.getStats()
        }
    }

    /**
     * 重置统计信息
     */
    resetStats(): void {
        this.stats = {
            totalProcessed: 0,
            totalErrors: 0,
            totalBatches: 0,
            averageBatchSize: 0,
            currentQueueSize: this.processingQueue.length,
            maxQueueSizeReached: 0,
            backpressureEvents: 0,
            processingTime: 0,
            parserStats: {}
        }

        this.parser.resetStats()
    }

    /**
     * 更新配置
     */
    updateOptions(options: Partial<LogStreamProcessorOptions>): void {
        this.options = { ...this.options, ...options as Required<LogStreamProcessorOptions> }

        // 重新设置批处理定时器
        this.setupBatchTimer()
    }

    /**
     * 强制处理所有队列中的日志
     */
    async flush(): Promise<void> {
        while (this.processingQueue.length > 0 || this.isProcessing) {
            await this.processBatch()
            await new Promise(resolve => setTimeout(resolve, 10)) // 小延迟避免忙等待
        }

        // 等待所有异步处理完成
        if (this.processingPromises.size > 0) {
            await Promise.allSettled(Array.from(this.processingPromises))
        }
    }

    /**
     * 清空队列
     */
    clearQueue(): void {
        this.processingQueue.length = 0
        this.updateQueueStats()
    }

    /**
     * 获取健康状态
     */
    getHealthStatus(): {
        isHealthy: boolean
        issues: string[]
        recommendations: string[]
    } {
        const issues: string[] = []
        const recommendations: string[] = []

        // 检查错误率
        const errorRate = this.stats.totalProcessed > 0 ?
            this.stats.totalErrors / (this.stats.totalProcessed + this.stats.totalErrors) : 0

        if (errorRate > 0.1) {
            issues.push(`错误率过高: ${(errorRate * 100).toFixed(1)}%`)
            recommendations.push('检查日志格式或增加错误恢复机制')
        }

        // 检查队列使用率
        const queueUsage = this.stats.currentQueueSize / this.options.maxQueueSize
        if (queueUsage > 0.8) {
            issues.push(`队列使用率过高: ${(queueUsage * 100).toFixed(1)}%`)
            recommendations.push('增加队列大小或提高处理速度')
        }

        // 检查背压事件
        if (this.stats.backpressureEvents > 0) {
            issues.push(`发生背压事件: ${this.stats.backpressureEvents}次`)
            recommendations.push('优化处理逻辑或增加批处理大小')
        }

        return {
            isHealthy: issues.length === 0,
            issues,
            recommendations
        }
    }

    /**
     * 销毁处理器
     */
    async destroy(): Promise<void> {
        // 清理定时器
        if (this.batchTimer) {
            clearInterval(this.batchTimer)
            this.batchTimer = undefined
        }

        // 处理剩余日志
        await this.flush()

        // 清空队列
        this.clearQueue()

        // 清理回调
        this.onProcessedLog = undefined
        this.onBatchProcessed = undefined
        this.onError = undefined

        // 销毁BackendLogPrinter
        if (this.backendLogPrinter) {
            await this.backendLogPrinter.destroy()
        }

        // 销毁FrontendLogAdapter
        if (this.frontendLogAdapter) {
            await this.frontendLogAdapter.destroy()
        }

        console.log('LogStreamProcessor已销毁')
    }

    /**
     * 初始化前端适配器
     */
    private async initializeFrontendAdapter(): Promise<void> {
        try {
            await this.frontendLogAdapter.initialize()
        } catch (error) {
            console.warn('LogStreamProcessor.initializeFrontendAdapter', '前端适配器初始化失败', error)
        }
    }

    /**
     * 启用/禁用打印机
     * @param enabled 是否启用
     */
    setPrinterEnabled(enabled: boolean): void {
        this.printerEnabled = enabled
    }

    /**
     * 获取打印机状态
     * @returns 是否启用
     */
    isPrinterEnabled(): boolean {
        return this.printerEnabled
    }

    /**
     * 获取BackendLogPrinter实例
     * @returns BackendLogPrinter实例
     */
    getBackendLogPrinter(): BackendLogPrinter {
        return this.backendLogPrinter
    }

    /**
     * 获取FrontendLogAdapter实例
     * @returns FrontendLogAdapter实例
     */
    getFrontendLogAdapter(): FrontendLogAdapter {
        return this.frontendLogAdapter
    }
}