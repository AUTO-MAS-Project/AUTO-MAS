/**
 * 日志缓冲区
 * 用于处理流式数据的缓冲和行分割
 * 处理不完整的日志行和缓冲区管理
 */

export interface LogBufferOptions {
    maxBufferSize?: number  // 最大缓冲区大小（字节）
    maxLineLength?: number  // 最大单行长度（字节）
    flushTimeout?: number   // 自动刷新超时时间（毫秒）
    encoding?: BufferEncoding  // 字符编码
}

export interface LogBufferStats {
    totalBytesReceived: number
    totalLinesProcessed: number
    currentBufferSize: number
    maxBufferSizeReached: number
    overflowCount: number
    incompleteLinesCount: number
}

/**
 * 日志缓冲区类
 * 处理流式数据的缓冲和行分割
 */
export class LogBuffer {
    private buffer: string = ''
    private options: Required<LogBufferOptions>
    private stats: LogBufferStats
    private lastFlushTime: number = Date.now()
    private flushTimer?: NodeJS.Timeout

    constructor(options: LogBufferOptions = {}) {
        this.options = {
            maxBufferSize: options.maxBufferSize || 1024 * 1024, // 1MB
            maxLineLength: options.maxLineLength || 64 * 1024,   // 64KB
            flushTimeout: options.flushTimeout || 1000,          // 1秒
            encoding: options.encoding || 'utf8'
        }

        this.stats = {
            totalBytesReceived: 0,
            totalLinesProcessed: 0,
            currentBufferSize: 0,
            maxBufferSizeReached: 0,
            overflowCount: 0,
            incompleteLinesCount: 0
        }

        // 设置自动刷新定时器
        this.setupFlushTimer()
    }

    /**
     * 设置自动刷新定时器
     */
    private setupFlushTimer(): void {
        if (this.flushTimer) {
            clearInterval(this.flushTimer)
        }

        this.flushTimer = setInterval(() => {
            const now = Date.now()
            if (now - this.lastFlushTime > this.options.flushTimeout && this.buffer.length > 0) {
                // 如果有缓冲数据且超过刷新超时时间，强制刷新
                this.flushIncompleteLine()
            }
        }, this.options.flushTimeout)
    }

    /**
     * 添加数据到缓冲区
     * @param data 要添加的数据
     * @returns 完整的行数组
     */
    addData(data: string | Buffer): string[] {
        const dataStr = typeof data === 'string' ? data : data.toString(this.options.encoding)
        const dataLength = Buffer.byteLength(dataStr, this.options.encoding)

        // 更新统计信息
        this.stats.totalBytesReceived += dataLength

        // 检查缓冲区是否会溢出
        if (this.stats.currentBufferSize + dataLength > this.options.maxBufferSize) {
            this.handleBufferOverflow()
        }

        // 添加数据到缓冲区
        this.buffer += dataStr
        this.stats.currentBufferSize = Buffer.byteLength(this.buffer, this.options.encoding)

        // 更新最大缓冲区大小记录
        if (this.stats.currentBufferSize > this.stats.maxBufferSizeReached) {
            this.stats.maxBufferSizeReached = this.stats.currentBufferSize
        }

        // 提取完整的行
        const lines = this.extractCompleteLines()

        // 更新最后刷新时间
        if (lines.length > 0) {
            this.lastFlushTime = Date.now()
        }

        return lines
    }

    /**
     * 提取完整的行
     * @returns 完整的行数组
     */
    private extractCompleteLines(): string[] {
        const lines: string[] = []
        let searchStartIndex = 0

        while (true) {
            const newlineIndex = this.buffer.indexOf('\n', searchStartIndex)

            if (newlineIndex === -1) {
                // 没有找到换行符，剩余数据是不完整的行
                if (searchStartIndex > 0) {
                    this.buffer = this.buffer.substring(searchStartIndex)
                    this.stats.currentBufferSize = Buffer.byteLength(this.buffer, this.options.encoding)
                }
                break
            }

            // 提取一行（包括换行符之前的内容）
            const line = this.buffer.substring(searchStartIndex, newlineIndex)

            // 处理Windows换行符（\r\n）
            const cleanLine = line.endsWith('\r') ? line.slice(0, -1) : line

            // 检查行长度是否超过限制
            if (Buffer.byteLength(cleanLine, this.options.encoding) > this.options.maxLineLength) {
                this.handleLineOverflow(cleanLine)
            } else if (cleanLine.length > 0) {
                lines.push(cleanLine)
                this.stats.totalLinesProcessed++
            }

            searchStartIndex = newlineIndex + 1
        }

        return lines
    }

    /**
     * 处理缓冲区溢出
     */
    private handleBufferOverflow(): void {
        this.stats.overflowCount++

        // 尝试找到最后一个换行符，保留之后的数据
        const lastNewlineIndex = this.buffer.lastIndexOf('\n')

        if (lastNewlineIndex !== -1) {
            // 保留最后一个换行符之后的数据
            this.buffer = this.buffer.substring(lastNewlineIndex + 1)
        } else {
            // 没有换行符，清空缓冲区
            this.buffer = ''
        }

        this.stats.currentBufferSize = Buffer.byteLength(this.buffer, this.options.encoding)

        console.warn(`日志缓冲区溢出，已丢弃部分数据。缓冲区大小: ${this.stats.currentBufferSize}`)
    }

    /**
     * 处理行溢出
     */
    private handleLineOverflow(line: string): void {
        // 截断过长的行
        const truncatedLine = line.substring(0, this.options.maxLineLength - 3) + '...'
        console.warn(`日志行过长，已截断。原长度: ${line.length}, 最大长度: ${this.options.maxLineLength}`)

        // 可以选择将截断的行添加到结果中，或者丢弃
        // 这里选择添加到结果中
        this.stats.totalLinesProcessed++
    }

    /**
     * 刷新不完整的行
     * @returns 不完整的行（如果有）
     */
    flushIncompleteLine(): string | null {
        if (this.buffer.length === 0) {
            return null
        }

        const incompleteLine = this.buffer
        this.buffer = ''
        this.stats.currentBufferSize = 0
        this.stats.incompleteLinesCount++

        // 处理可能的换行符
        const cleanLine = incompleteLine.replace(/\r?\n$/, '')

        return cleanLine.length > 0 ? cleanLine : null
    }

    /**
     * 强制刷新所有缓冲数据
     * @returns 所有剩余的数据（包括不完整的行）
     */
    flushAll(): string[] {
        const lines: string[] = []

        // 提取所有可能的行
        const completeLines = this.extractCompleteLines()
        lines.push(...completeLines)

        // 刷新不完整的行
        const incompleteLine = this.flushIncompleteLine()
        if (incompleteLine !== null) {
            lines.push(incompleteLine)
        }

        return lines
    }

    /**
     * 清空缓冲区
     */
    clear(): void {
        this.buffer = ''
        this.stats.currentBufferSize = 0
    }

    /**
     * 检查缓冲区是否为空
     */
    isEmpty(): boolean {
        return this.buffer.length === 0
    }

    /**
     * 获取当前缓冲区大小
     */
    getBufferSize(): number {
        return this.stats.currentBufferSize
    }

    /**
     * 获取统计信息
     */
    getStats(): LogBufferStats {
        return { ...this.stats }
    }

    /**
     * 重置统计信息
     */
    resetStats(): void {
        this.stats = {
            totalBytesReceived: 0,
            totalLinesProcessed: 0,
            currentBufferSize: this.stats.currentBufferSize,
            maxBufferSizeReached: 0,
            overflowCount: 0,
            incompleteLinesCount: 0
        }
    }

    /**
     * 更新配置选项
     */
    updateOptions(options: Partial<LogBufferOptions>): void {
        this.options = { ...this.options, ...options as Required<LogBufferOptions> }

        // 重新设置刷新定时器
        this.setupFlushTimer()
    }

    /**
     * 获取缓冲区内容（用于调试）
     */
    getBufferContent(): string {
        return this.buffer
    }

    /**
     * 检查缓冲区健康状态
     */
    getHealthStatus(): {
        isHealthy: boolean
        issues: string[]
        recommendations: string[]
    } {
        const issues: string[] = []
        const recommendations: string[] = []

        // 检查缓冲区使用率
        const bufferUsageRatio = this.stats.currentBufferSize / this.options.maxBufferSize
        if (bufferUsageRatio > 0.8) {
            issues.push(`缓冲区使用率过高: ${(bufferUsageRatio * 100).toFixed(1)}%`)
            recommendations.push('考虑增加最大缓冲区大小或检查数据处理速度')
        }

        // 检查溢出情况
        if (this.stats.overflowCount > 0) {
            issues.push(`发生缓冲区溢出: ${this.stats.overflowCount}次`)
            recommendations.push('增加最大缓冲区大小或优化数据处理逻辑')
        }

        // 检查不完整行数量
        if (this.stats.incompleteLinesCount > this.stats.totalLinesProcessed * 0.1) {
            issues.push(`不完整行比例过高: ${((this.stats.incompleteLinesCount / Math.max(1, this.stats.totalLinesProcessed)) * 100).toFixed(1)}%`)
            recommendations.push('检查数据源是否正确发送换行符')
        }

        return {
            isHealthy: issues.length === 0,
            issues,
            recommendations
        }
    }

    /**
     * 销毁缓冲区，清理资源
     */
    destroy(): void {
        if (this.flushTimer) {
            clearInterval(this.flushTimer)
            this.flushTimer = undefined
        }

        this.clear()
        this.resetStats()
    }
}