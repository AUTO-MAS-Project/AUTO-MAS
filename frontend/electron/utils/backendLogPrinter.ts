/**
 * 后端日志打印器
 * 集成 LogLevelMapper 和 BackendLogFormatter
 * 实现前端界面输出
 * 支持异步打印和批量打印
 * 添加打印过滤和条件判断
 */

import { ParsedLogEntry, LogLevel } from '../types/log'
import { LogLevelMapper } from './logLevelMapper'

/**
 * 打印选项接口
 */
export interface PrintOptions {
    // 是否启用前端输出
    enableFrontend?: boolean
    // 最小打印级别
    minLevel?: LogLevel
    // 最大打印级别
    maxLevel?: LogLevel
    // 是否启用异步打印
    enableAsync?: boolean
    // 批量打印大小
    batchSize?: number
    // 批量打印超时（毫秒）
    batchTimeout?: number
    // 是否启用打印过滤
    enableFilter?: boolean
    // 过滤条件
    filter?: (log: ParsedLogEntry) => boolean
}

/**
 * 打印统计信息接口
 */
export interface PrintStats {
    // 总打印数量
    totalPrinted: number
    // 前端打印数量
    frontendPrinted: number
    // 过滤掉的数量
    filteredCount: number
    // 错误数量
    errorCount: number
    // 平均打印时间（毫秒）
    averagePrintTime: number
    // 批量打印统计
    batchStats: {
        totalBatches: number
        averageBatchSize: number
        maxBatchSize: number
    }
}

/**
 * 打印结果接口
 */
export interface PrintResult {
    // 是否成功
    success: boolean
    // 打印的消息
    message?: string
    // 错误信息
    error?: string
    // 打印耗时（毫秒）
    printTime: number
    // 打印的目标
    targets: string[]
}

/**
 * 后端日志打印器类
 */
export class BackendLogPrinter {
    private static instance: BackendLogPrinter
    private levelMapper: LogLevelMapper
    private options: Required<PrintOptions>
    private stats: PrintStats
    private printQueue: ParsedLogEntry[] = []
    private batchTimer?: NodeJS.Timeout
    private isPrinting: boolean = false
    private printPromises: Set<Promise<void>> = new Set()

    private constructor(levelMapper?: LogLevelMapper) {
        this.levelMapper = levelMapper || LogLevelMapper.getInstance()

        this.options = {
            enableFrontend: true,  // 只保留前端输出
            minLevel: LogLevel.TRACE,
            maxLevel: LogLevel.CRITICAL,
            enableAsync: true,
            batchSize: 50,
            batchTimeout: 500,
            enableFilter: false,
            filter: () => true
        }

        this.stats = {
            totalPrinted: 0,
            frontendPrinted: 0,
            filteredCount: 0,
            errorCount: 0,
            averagePrintTime: 0,
            batchStats: {
                totalBatches: 0,
                averageBatchSize: 0,
                maxBatchSize: 0
            }
        }

        // 启动批处理定时器
        this.setupBatchTimer()
    }

    /**
     * 获取单例实例
     */
    static getInstance(levelMapper?: LogLevelMapper): BackendLogPrinter {
        if (!BackendLogPrinter.instance) {
            BackendLogPrinter.instance = new BackendLogPrinter(levelMapper)
        }
        return BackendLogPrinter.instance
    }

    /**
     * 打印单个日志条目
     * @param parsedLog 解析后的日志条目
     * @param options 打印选项
     * @returns 打印结果
     */
    print(parsedLog: ParsedLogEntry, options: Partial<PrintOptions> = {}): PrintResult {
        const startTime = Date.now()
        const mergedOptions = { ...this.options, ...options } as Required<PrintOptions>

        try {
            // 验证日志条目
            if (!this.validateLogEntry(parsedLog)) {
                this.stats.filteredCount++
                return {
                    success: false,
                    message: '日志条目验证失败',
                    printTime: Date.now() - startTime,
                    targets: []
                }
            }

            // 应用级别过滤
            if (!this.isLevelInRange(parsedLog.level, mergedOptions.minLevel, mergedOptions.maxLevel)) {
                this.stats.filteredCount++
                return {
                    success: false,
                    message: '日志级别不在范围内',
                    printTime: Date.now() - startTime,
                    targets: []
                }
            }

            // 应用自定义过滤
            if (mergedOptions.enableFilter && !mergedOptions.filter(parsedLog)) {
                this.stats.filteredCount++
                return {
                    success: false,
                    message: '日志被自定义过滤器过滤',
                    printTime: Date.now() - startTime,
                    targets: []
                }
            }

            // 异步打印
            if (mergedOptions.enableAsync) {
                this.printAsync(parsedLog, mergedOptions)
                return {
                    success: true,
                    message: '已加入异步打印队列',
                    printTime: Date.now() - startTime,
                    targets: this.getEnabledTargets(mergedOptions)
                }
            }

            // 同步打印
            const targets = this.printSync(parsedLog, mergedOptions)
            this.updateStats(Date.now() - startTime, targets.length)

            return {
                success: true,
                message: '打印成功',
                printTime: Date.now() - startTime,
                targets
            }
        } catch (error) {
            this.stats.errorCount++
            const errorMessage = error instanceof Error ? error.message : String(error)
            console.error('BackendLogPrinter.print', '打印失败', errorMessage, parsedLog)

            return {
                success: false,
                error: errorMessage,
                printTime: Date.now() - startTime,
                targets: []
            }
        }
    }

    /**
     * 批量打印日志条目
     * @param parsedLogs 解析后的日志条目数组
     * @param options 打印选项
     * @returns 打印结果数组
     */
    printBatch(parsedLogs: ParsedLogEntry[], options: Partial<PrintOptions> = {}): PrintResult[] {
        const mergedOptions = { ...this.options, ...options } as Required<PrintOptions>
        const results: PrintResult[] = []

        try {
            if (mergedOptions.enableAsync) {
                // 异步批量打印
                this.printBatchAsync(parsedLogs, mergedOptions)
                results.push({
                    success: true,
                    message: `已加入异步批量打印队列，共${parsedLogs.length}条日志`,
                    printTime: 0,
                    targets: this.getEnabledTargets(mergedOptions)
                })
            } else {
                // 同步批量打印
                const startTime = Date.now()
                const allTargets = new Set<string>()

                for (const log of parsedLogs) {
                    const result = this.print(log, { ...mergedOptions, enableAsync: false })
                    results.push(result)
                    result.targets.forEach(target => allTargets.add(target))
                }

                const totalTime = Date.now() - startTime
                this.updateBatchStats(parsedLogs.length, totalTime)

                // 添加批量统计结果
                results.unshift({
                    success: true,
                    message: `批量打印完成，共${parsedLogs.length}条日志`,
                    printTime: totalTime,
                    targets: Array.from(allTargets)
                })
            }
        } catch (error) {
            const errorMessage = error instanceof Error ? error.message : String(error)
            console.error('BackendLogPrinter.printBatch', '批量打印失败', errorMessage)

            results.push({
                success: false,
                error: errorMessage,
                printTime: 0,
                targets: []
            })
        }

        return results
    }

    /**
     * 设置打印选项
     * @param options 打印选项
     */
    setOptions(options: Partial<PrintOptions>): void {
        this.options = { ...this.options, ...options } as Required<PrintOptions>

        // 重新设置批处理定时器
        if (options.batchTimeout !== undefined) {
            this.setupBatchTimer()
        }
    }

    /**
     * 获取当前选项
     * @returns 当前选项
     */
    getOptions(): Required<PrintOptions> {
        return { ...this.options }
    }

    /**
     * 获取打印统计信息
     * @returns 统计信息
     */
    getStats(): PrintStats {
        return { ...this.stats }
    }

    /**
     * 重置统计信息
     */
    resetStats(): void {
        this.stats = {
            totalPrinted: 0,
            frontendPrinted: 0,
            filteredCount: 0,
            errorCount: 0,
            averagePrintTime: 0,
            batchStats: {
                totalBatches: 0,
                averageBatchSize: 0,
                maxBatchSize: 0
            }
        }
    }

    /**
     * 强制刷新打印队列
     */
    async flush(): Promise<void> {
        if (this.printQueue.length > 0) {
            await this.processBatch()
        }

        // 等待所有异步打印完成
        if (this.printPromises.size > 0) {
            await Promise.allSettled(Array.from(this.printPromises))
        }
    }

    /**
     * 验证日志条目
     * @param parsedLog 解析后的日志条目
     * @returns 是否有效
     */
    private validateLogEntry(parsedLog: ParsedLogEntry): boolean {
        return !!(parsedLog &&
            parsedLog.timestamp &&
            parsedLog.level &&
            parsedLog.module &&
            parsedLog.message)
    }

    /**
     * 检查日志级别是否在范围内
     * @param level 日志级别
     * @param minLevel 最小级别
     * @param maxLevel 最大级别
     * @returns 是否在范围内
     */
    private isLevelInRange(level: LogLevel, minLevel: LogLevel, maxLevel: LogLevel): boolean {
        const levelOrder = [LogLevel.TRACE, LogLevel.DEBUG, LogLevel.INFO, LogLevel.WARN, LogLevel.ERROR, LogLevel.CRITICAL, LogLevel.SUCCESS]
        const levelIndex = levelOrder.indexOf(level)
        const minIndex = levelOrder.indexOf(minLevel)
        const maxIndex = levelOrder.indexOf(maxLevel)

        return levelIndex >= minIndex && levelIndex <= maxIndex
    }

    /**
     * 获取启用的打印目标
     * @param options 打印选项
     * @returns 目标数组
     */
    private getEnabledTargets(options: Required<PrintOptions>): string[] {
        const targets: string[] = []

        if (options.enableFrontend) targets.push('frontend')

        return targets
    }

    /**
     * 同步打印
     * @param parsedLog 解析后的日志条目
     * @param options 打印选项
     * @returns 打印目标数组
     */
    private printSync(parsedLog: ParsedLogEntry, options: Required<PrintOptions>): string[] {
        const targets: string[] = []

        // 只保留前端输出
        if (options.enableFrontend) {
            this.printToFrontend(parsedLog)
            targets.push('frontend')
            this.stats.frontendPrinted++
        }

        this.stats.totalPrinted++
        return targets
    }

    /**
     * 异步打印
     * @param parsedLog 解析后的日志条目
     * @param options 打印选项
     */
    private printAsync(parsedLog: ParsedLogEntry, options: Required<PrintOptions>): void {
        // 添加到打印队列
        this.printQueue.push(parsedLog)

        // 如果队列大小达到批量大小，立即处理
        if (this.printQueue.length >= options.batchSize) {
            this.processBatch()
        }
    }

    /**
     * 异步批量打印
     * @param parsedLogs 解析后的日志条目数组
     * @param options 打印选项
     */
    private printBatchAsync(parsedLogs: ParsedLogEntry[], options: Required<PrintOptions>): void {
        // 添加到打印队列
        this.printQueue.push(...parsedLogs)

        // 立即处理
        this.processBatch()
    }

    /**
     * 处理批量打印
     */
    private async processBatch(): Promise<void> {
        if (this.isPrinting || this.printQueue.length === 0) {
            return
        }

        this.isPrinting = true
        const startTime = Date.now()

        try {
            // 取出一批日志
            const batch = this.printQueue.splice(0, this.options.batchSize)

            // 更新批量统计
            this.updateBatchStats(batch.length, Date.now() - startTime)

            // 创建打印Promise
            const printPromise = new Promise<void>((resolve) => {
                // 使用setImmediate避免阻塞主线程
                setImmediate(() => {
                    try {
                        for (const log of batch) {
                            this.printSync(log, this.options)
                        }
                        resolve()
                    } catch (error) {
                        console.error('BackendLogPrinter.processBatch', '批量打印处理失败', error)
                        resolve()
                    }
                })
            })

            this.printPromises.add(printPromise)
            printPromise.finally(() => {
                this.printPromises.delete(printPromise)
            })

            await printPromise
        } finally {
            this.isPrinting = false
        }
    }

    /**
     * 打印到前端
     * @param parsedLog 解析后的日志条目
     */
    private printToFrontend(parsedLog: ParsedLogEntry): void {
        // 直接调用前端日志方法，不使用格式化器
        // 使用logService的对应级别方法
        const { logService } = require('../services/logService')

        switch (parsedLog.level) {
            case 'TRACE':
                logService.debug(parsedLog.module, parsedLog.message)
                break
            case 'DEBUG':
                logService.debug(parsedLog.module, parsedLog.message)
                break
            case 'INFO':
                logService.info(parsedLog.module, parsedLog.message)
                break
            case 'WARN':
                logService.warn(parsedLog.module, parsedLog.message)
                break
            case 'ERROR':
                logService.error(parsedLog.module, parsedLog.message)
                break
            case 'CRITICAL':
                logService.error(parsedLog.module, parsedLog.message)
                break
            case 'SUCCESS':
                logService.info(parsedLog.module, parsedLog.message)
                break
            default:
                logService.info(parsedLog.module, parsedLog.message)
                break
        }
    }

    /**
     * 设置批处理定时器
     */
    private setupBatchTimer(): void {
        if (this.batchTimer) {
            clearInterval(this.batchTimer)
        }

        this.batchTimer = setInterval(() => {
            if (this.printQueue.length > 0) {
                this.processBatch()
            }
        }, this.options.batchTimeout)
    }

    /**
     * 更新统计信息
     * @param printTime 打印时间
     * @param targetCount 目标数量
     */
    private updateStats(printTime: number, targetCount: number): void {
        this.stats.totalPrinted += targetCount

        // 更新平均打印时间
        if (this.stats.totalPrinted === 1) {
            this.stats.averagePrintTime = printTime
        } else {
            this.stats.averagePrintTime =
                (this.stats.averagePrintTime * (this.stats.totalPrinted - targetCount) + printTime) /
                this.stats.totalPrinted
        }
    }

    /**
     * 更新批量统计信息
     * @param batchSize 批量大小
     * @param totalTime 总时间
     */
    private updateBatchStats(batchSize: number, totalTime: number): void {
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
     * 处理打印错误
     * @param error 错误对象
     * @param parsedLog 解析后的日志条目
     */
    private handlePrintError(error: Error, parsedLog: ParsedLogEntry): void {
        this.stats.errorCount++
        console.error('BackendLogPrinter', '打印错误', error.message, parsedLog)
    }

    /**
     * 销毁打印器
     */
    async destroy(): Promise<void> {
        // 清理定时器
        if (this.batchTimer) {
            clearInterval(this.batchTimer)
            this.batchTimer = undefined
        }

        // 刷新剩余队列
        await this.flush()

        // 清空队列
        this.printQueue = []

        console.log('BackendLogPrinter已销毁')
    }
}

// 导出单例实例
export const backendLogPrinter = BackendLogPrinter.getInstance()

// 导出便捷函数
export const printBackendLog = (parsedLog: ParsedLogEntry, options?: Partial<PrintOptions>): PrintResult => {
    return backendLogPrinter.print(parsedLog, options)
}

export const printBackendLogs = (parsedLogs: ParsedLogEntry[], options?: Partial<PrintOptions>): PrintResult[] => {
    return backendLogPrinter.printBatch(parsedLogs, options)
}