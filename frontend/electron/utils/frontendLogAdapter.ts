/**
 * 前端日志适配器
 * 集成现有的 logService 和 logManagementService
 * 实现向前端界面发送日志的功能
 * 支持日志订阅和实时更新
 * 添加错误处理和降级机制
 */

import { EventEmitter } from 'events'
import { ParsedLogEntry, LogSource } from '../types/log'
import { LogLevel } from './logColors'

/**
 * 适配器配置接口
 */
export interface FrontendLogAdapterConfig {
    // 是否启用控制台输出
    enableConsole?: boolean
    // 是否启用文件输出
    enableFile?: boolean
    // 是否启用前端界面输出
    enableFrontend?: boolean
    // 是否启用IPC通信
    enableIPC?: boolean
    // 是否启用日志缓冲
    enableBuffer?: boolean
    // 缓冲区大小
    bufferSize?: number
    // 缓冲刷新间隔（毫秒）
    bufferFlushInterval?: number
    // 是否启用批量发送
    enableBatch?: boolean
    // 批量发送大小
    batchSize?: number
    // 是否启用错误恢复
    enableErrorRecovery?: boolean
    // 最大重试次数
    maxRetryAttempts?: number
    // 重试延迟（毫秒）
    retryDelay?: number
}

/**
 * 适配器统计信息接口
 */
export interface AdapterStats {
    // 总处理数量
    totalProcessed: number
    // 控制台输出数量
    consoleOutput: number
    // 文件输出数量
    fileOutput: number
    // 前端输出数量
    frontendOutput: number
    // 错误数量
    errorCount: number
    // 重试数量
    retryCount: number
    // 缓冲区统计
    bufferStats: {
        size: number
        maxSize: number
        flushCount: number
    }
    // 批量统计
    batchStats: {
        totalBatches: number
        averageBatchSize: number
        maxBatchSize: number
    }
}

/**
 * 前端日志适配器类
 */
export class FrontendLogAdapter extends EventEmitter {
    private static instance: FrontendLogAdapter
    private config: Required<FrontendLogAdapterConfig>
    private stats: AdapterStats
    private logBuffer: ParsedLogEntry[] = []
    private batchTimer?: NodeJS.Timeout
    private isProcessing: boolean = false
    private retryQueue: Array<{ log: ParsedLogEntry; attempts: number }> = []

    // 服务引用（延迟加载）
    private logService: any = null
    private logManagementService: any = null
    private mainWindow: any = null

    private constructor(config: FrontendLogAdapterConfig = {}) {
        super()

        this.config = {
            enableConsole: false,  // 禁用控制台输出（避免重复，logService 会输出）
            enableFile: false,     // 禁用文件输出（避免重复写入）
            enableFrontend: true,  // 保留前端输出
            enableIPC: true,
            enableBuffer: true,
            bufferSize: 1000,
            bufferFlushInterval: 1000,
            enableBatch: true,
            batchSize: 50,
            enableErrorRecovery: true,
            maxRetryAttempts: 3,
            retryDelay: 1000,
            ...config
        } as Required<FrontendLogAdapterConfig>

        this.stats = {
            totalProcessed: 0,
            consoleOutput: 0,
            fileOutput: 0,
            frontendOutput: 0,
            errorCount: 0,
            retryCount: 0,
            bufferStats: {
                size: 0,
                maxSize: 0,
                flushCount: 0
            },
            batchStats: {
                totalBatches: 0,
                averageBatchSize: 0,
                maxBatchSize: 0
            }
        }

        // 启动缓冲刷新定时器
        if (this.config.enableBuffer) {
            this.setupBufferTimer()
        }
    }

    /**
     * 获取单例实例
     */
    static getInstance(config?: FrontendLogAdapterConfig): FrontendLogAdapter {
        if (!FrontendLogAdapter.instance) {
            FrontendLogAdapter.instance = new FrontendLogAdapter(config)
        }
        return FrontendLogAdapter.instance
    }

    /**
     * 初始化适配器
     */
    async initialize(): Promise<void> {
        try {
            // 延迟加载服务
            await this.loadServices()

            // 设置事件监听
            this.setupEventListeners()

            // 处理重试队列
            this.processRetryQueue()

            this.emit('initialized')
        } catch (error) {
            this.handleError(error instanceof Error ? error : new Error(String(error)))
            throw error
        }
    }

    /**
     * 打印日志
     * @param level 日志级别
     * @param module 模块名
     * @param message 日志消息
     * @param source 日志来源
     * @param metadata 元数据
     */
    async print(
        level: LogLevel,
        module: string,
        message: string,
        source: LogSource = LogSource.BACKEND,
        metadata?: Record<string, any>
    ): Promise<void> {
        const logEntry: ParsedLogEntry = {
            timestamp: new Date(),
            level,
            module,
            message,
            source,
            metadata,
            originalLog: message,
            isValid: true
        }

        await this.processLogEntry(logEntry)
    }

    /**
     * 处理日志条目
     * @param logEntry 日志条目
     */
    async processLogEntry(logEntry: ParsedLogEntry): Promise<void> {
        this.stats.totalProcessed++

        try {
            // 添加到缓冲区
            if (this.config.enableBuffer) {
                this.addToBuffer(logEntry)
                return
            }

            // 直接处理
            await this.processDirectly(logEntry)
        } catch (error) {
            this.handleError(error instanceof Error ? error : new Error(String(error)))

            // 错误恢复
            if (this.config.enableErrorRecovery) {
                this.addToRetryQueue(logEntry)
            }
        }
    }

    /**
     * 批量处理日志条目
     * @param logEntries 日志条目数组
     */
    async processBatch(logEntries: ParsedLogEntry[]): Promise<void> {
        this.stats.totalProcessed += logEntries.length

        try {
            // 更新批量统计
            this.updateBatchStats(logEntries.length)

            // 批量处理
            const promises: Promise<void>[] = []

            if (this.config.enableConsole) {
                promises.push(this.batchPrintToConsole(logEntries))
            }

            if (this.config.enableFile) {
                promises.push(this.batchPrintToFile(logEntries))
            }

            if (this.config.enableFrontend) {
                promises.push(this.batchPrintToFrontend(logEntries))
            }

            await Promise.allSettled(promises)

            this.emit('batch-processed', logEntries)
        } catch (error) {
            this.handleError(error instanceof Error ? error : new Error(String(error)))

            // 错误恢复
            if (this.config.enableErrorRecovery) {
                for (const logEntry of logEntries) {
                    this.addToRetryQueue(logEntry)
                }
            }
        }
    }

    /**
     * 设置配置
     * @param config 配置
     */
    setConfig(config: Partial<FrontendLogAdapterConfig>): void {
        this.config = { ...this.config, ...config } as Required<FrontendLogAdapterConfig>

        // 重新设置缓冲定时器
        if (config.bufferFlushInterval !== undefined) {
            this.setupBufferTimer()
        }
    }

    /**
     * 获取配置
     * @returns 当前配置
     */
    getConfig(): Required<FrontendLogAdapterConfig> {
        return { ...this.config }
    }

    /**
     * 获取统计信息
     * @returns 统计信息
     */
    getStats(): AdapterStats {
        return { ...this.stats }
    }

    /**
     * 重置统计信息
     */
    resetStats(): void {
        this.stats = {
            totalProcessed: 0,
            consoleOutput: 0,
            fileOutput: 0,
            frontendOutput: 0,
            errorCount: 0,
            retryCount: 0,
            bufferStats: {
                size: this.logBuffer.length,
                maxSize: this.stats.bufferStats.maxSize,
                flushCount: 0
            },
            batchStats: {
                totalBatches: 0,
                averageBatchSize: 0,
                maxBatchSize: 0
            }
        }
    }

    /**
     * 强制刷新缓冲区
     */
    async flush(): Promise<void> {
        if (this.logBuffer.length > 0) {
            await this.flushBuffer()
        }
    }

    /**
     * 销毁适配器
     */
    async destroy(): Promise<void> {
        // 清理定时器
        if (this.batchTimer) {
            clearInterval(this.batchTimer)
            this.batchTimer = undefined
        }

        // 刷新缓冲区
        await this.flush()

        // 清空缓冲区
        this.logBuffer = []
        this.retryQueue = []

        // 移除所有监听器
        this.removeAllListeners()

        console.log('FrontendLogAdapter已销毁')
    }

    /**
     * 加载服务
     */
    private async loadServices(): Promise<void> {
        try {
            // 动态导入服务
            const { logService } = await import('../services/logService')
            this.logService = logService

            const { logManagementService } = await import('../services/logManagementService')
            this.logManagementService = logManagementService

            // 获取主窗口引用
            const { BrowserWindow } = await import('electron')
            this.mainWindow = BrowserWindow.getFocusedWindow() || (BrowserWindow as any).getAllWindows()[0]
        } catch (error) {
            console.warn('FrontendLogAdapter.loadServices', '服务加载失败，将使用降级模式', error)
        }
    }

    /**
     * 设置事件监听
     */
    private setupEventListeners(): void {
        // 监听错误事件
        this.on('error', (error) => {
            console.error('FrontendLogAdapter错误', error)
        })
    }

    /**
     * 添加到缓冲区
     * @param logEntry 日志条目
     */
    private addToBuffer(logEntry: ParsedLogEntry): void {
        this.logBuffer.push(logEntry)

        // 限制缓冲区大小
        if (this.logBuffer.length > this.config.bufferSize) {
            this.logBuffer = this.logBuffer.slice(-this.config.bufferSize)
        }

        // 更新缓冲区统计
        this.stats.bufferStats.size = this.logBuffer.length
        if (this.stats.bufferStats.size > this.stats.bufferStats.maxSize) {
            this.stats.bufferStats.maxSize = this.stats.bufferStats.size
        }

        // 如果达到批量大小，立即刷新
        if (this.config.enableBatch && this.logBuffer.length >= this.config.batchSize) {
            this.flushBuffer()
        }
    }

    /**
     * 刷新缓冲区
     */
    private async flushBuffer(): Promise<void> {
        if (this.isProcessing || this.logBuffer.length === 0) {
            return
        }

        this.isProcessing = true

        try {
            // 取出一批日志
            const batch = this.logBuffer.splice(0, this.config.batchSize)

            // 处理批量日志
            await this.processBatch(batch)

            // 更新缓冲区统计
            this.stats.bufferStats.flushCount++
            this.stats.bufferStats.size = this.logBuffer.length
        } finally {
            this.isProcessing = false
        }
    }

    /**
     * 直接处理日志条目
     * @param logEntry 日志条目
     */
    private async processDirectly(logEntry: ParsedLogEntry): Promise<void> {
        // 只保留前端输出
        if (this.config.enableFrontend) {
            await this.printToFrontend(logEntry)
        }
    }

    /**
     * 打印到控制台
     * @param logEntry 日志条目
     */
    private async printToConsole(logEntry: ParsedLogEntry): Promise<void> {
        try {
            if (this.logService) {
                // 使用logService
                this.logService.writeLog(logEntry.level, logEntry.module, logEntry.message)
            } else {
                // 降级到console
                console.log(`[${logEntry.level}] [${logEntry.module}] ${logEntry.message}`)
            }

            this.stats.consoleOutput++
        } catch (error) {
            throw new Error(`控制台输出失败: ${error}`)
        }
    }

    /**
     * 批量打印到控制台
     * @param logEntries 日志条目数组
     */
    private async batchPrintToConsole(logEntries: ParsedLogEntry[]): Promise<void> {
        try {
            if (this.logService) {
                // 使用logService批量写入
                for (const logEntry of logEntries) {
                    this.logService.writeLog(logEntry.level, logEntry.module, logEntry.message)
                }
            } else {
                // 降级到console
                for (const logEntry of logEntries) {
                    console.log(`[${logEntry.level}] [${logEntry.module}] ${logEntry.message}`)
                }
            }

            this.stats.consoleOutput += logEntries.length
        } catch (error) {
            throw new Error(`批量控制台输出失败: ${error}`)
        }
    }

    /**
     * 打印到文件
     * @param logEntry 日志条目
     */
    private async printToFile(logEntry: ParsedLogEntry): Promise<void> {
        try {
            if (this.logService) {
                // 使用logService写入文件
                this.logService.writeLog(logEntry.level, logEntry.module, logEntry.message)
            } else {
            }

            this.stats.fileOutput++
        } catch (error) {
            throw new Error(`文件输出失败: ${error}`)
        }
    }

    /**
     * 批量打印到文件
     * @param logEntries 日志条目数组
     */
    private async batchPrintToFile(logEntries: ParsedLogEntry[]): Promise<void> {
        try {
            if (this.logService) {
                // 使用logService批量写入文件
                for (const logEntry of logEntries) {
                    this.logService.writeLog(logEntry.level, logEntry.module, logEntry.message)
                }
            } else {
                // 降级模式，暂时使用console
                for (const logEntry of logEntries) {
                }
            }

            this.stats.fileOutput += logEntries.length
        } catch (error) {
            throw new Error(`批量文件输出失败: ${error}`)
        }
    }

    /**
     * 打印到前端
     * @param logEntry 日志条目
     */
    private async printToFrontend(logEntry: ParsedLogEntry): Promise<void> {
        try {
            // 直接调用前端日志方法，不使用IPC或logManagementService
            const { logService } = require('../services/logService')

            // 使用 writeLog 方法，直接传递 source 参数
            logService.writeLog(logEntry.level, logEntry.module, logEntry.message, logEntry.source)

            this.stats.frontendOutput++
        } catch (error) {
            console.error('[FrontendLogAdapter.printToFrontend] 错误:', error)
            throw new Error(`前端输出失败: ${error}`)
        }
    }

    /**
     * 批量打印到前端
     * @param logEntries 日志条目数组
     */
    private async batchPrintToFrontend(logEntries: ParsedLogEntry[]): Promise<void> {
        try {
            // 直接调用前端日志方法，不使用IPC或logManagementService
            const { logService } = require('../services/logService')

            // 使用 writeLog 方法批量处理，直接传递 source 参数
            for (const logEntry of logEntries) {
                logService.writeLog(logEntry.level, logEntry.module, logEntry.message, logEntry.source)
            }

            this.stats.frontendOutput += logEntries.length
        } catch (error) {
            throw new Error(`批量前端输出失败: ${error}`)
        }
    }

    /**
     * 设置缓冲定时器
     */
    private setupBufferTimer(): void {
        if (this.batchTimer) {
            clearInterval(this.batchTimer)
        }

        this.batchTimer = setInterval(() => {
            if (this.logBuffer.length > 0) {
                this.flushBuffer()
            }
        }, this.config.bufferFlushInterval)
    }

    /**
     * 添加到重试队列
     * @param logEntry 日志条目
     */
    private addToRetryQueue(logEntry: ParsedLogEntry): void {
        this.retryQueue.push({
            log: logEntry,
            attempts: 0
        })
    }

    /**
     * 处理重试队列
     */
    private async processRetryQueue(): Promise<void> {
        if (this.retryQueue.length === 0) {
            return
        }

        const retryPromises: Promise<void>[] = []
        const remainingRetries: Array<{ log: ParsedLogEntry; attempts: number }> = []

        for (const item of this.retryQueue) {
            if (item.attempts < this.config.maxRetryAttempts) {
                retryPromises.push(this.retryLogEntry(item))
            } else {
                remainingRetries.push(item)
            }
        }

        // 更新重试队列
        this.retryQueue = remainingRetries

        // 执行重试
        await Promise.allSettled(retryPromises)

        // 如果还有重试项，延迟后继续处理
        if (this.retryQueue.length > 0) {
            setTimeout(() => this.processRetryQueue(), this.config.retryDelay)
        }
    }

    /**
     * 重试日志条目
     * @param item 重试项
     */
    private async retryLogEntry(item: { log: ParsedLogEntry; attempts: number }): Promise<void> {
        try {
            item.attempts++
            this.stats.retryCount++

            await this.processLogEntry(item.log)
        } catch (error) {
            // 重试失败，重新加入队列
            this.addToRetryQueue(item.log)
        }
    }

    /**
     * 更新批量统计
     * @param batchSize 批量大小
     */
    private updateBatchStats(batchSize: number): void {
        this.stats.batchStats.totalBatches++

        // 更新平均批量大小
        if (this.stats.batchStats.totalBatches === 1) {
            this.stats.batchStats.averageBatchSize = batchSize
        } else {
            this.stats.batchStats.averageBatchSize =
                (this.stats.batchStats.averageBatchSize * (this.stats.batchStats.totalBatches - 1) + batchSize) /
                this.stats.batchStats.totalBatches
        }

        // 更新最大批量大小
        if (batchSize > this.stats.batchStats.maxBatchSize) {
            this.stats.batchStats.maxBatchSize = batchSize
        }
    }

    /**
     * 处理错误
     * @param error 错误对象
     */
    private handleError(error: Error): void {
        this.stats.errorCount++
        this.emit('error', error)
        console.error('FrontendLogAdapter错误', error.message)
    }
}

// 导出单例实例
export const frontendLogAdapter = FrontendLogAdapter.getInstance()

// 导出便捷函数
export const printToFrontend = (
    level: LogLevel,
    module: string,
    message: string,
    source?: LogSource,
    metadata?: Record<string, any>
): Promise<void> => {
    return frontendLogAdapter.print(level, module, message, source, metadata)
}

export const processLogEntry = (logEntry: ParsedLogEntry): Promise<void> => {
    return frontendLogAdapter.processLogEntry(logEntry)
}

export const processBatchLogEntries = (logEntries: ParsedLogEntry[]): Promise<void> => {
    return frontendLogAdapter.processBatch(logEntries)
}