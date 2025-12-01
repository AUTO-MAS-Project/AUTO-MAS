/**
 * 后端日志捕获器
 * 用于捕获后端进程的stdout/stderr流
 * 使用LogBuffer进行流式数据缓冲
 * 提供开始/停止捕获的方法
 * 处理进程断开和重连逻辑
 */

import { ChildProcessWithoutNullStreams } from 'child_process'
import { LogBuffer, LogBufferOptions } from './logBuffer'

export interface BackendLogCaptureOptions {
    bufferOptions?: LogBufferOptions
    autoReconnect?: boolean
    reconnectInterval?: number
    maxReconnectAttempts?: number
    enableErrorRecovery?: boolean
}

export interface LogCaptureStats {
    totalBytesCaptured: number
    totalLinesCaptured: number
    captureStartTime?: Date
    lastCaptureTime?: Date
    reconnectCount: number
    errorCount: number
    bufferStats: any
}

export type LogLineCallback = (line: string, source: 'stdout' | 'stderr') => void
export type ErrorCallback = (error: Error) => void
export type StatusCallback = (isCapturing: boolean) => void

/**
 * 后端日志捕获器类
 */
export class BackendLogCapture {
    private process: ChildProcessWithoutNullStreams | null = null
    private stdoutBuffer: LogBuffer
    private stderrBuffer: LogBuffer
    private options: Required<BackendLogCaptureOptions>
    private isCapturing: boolean = false
    private stats: LogCaptureStats
    private reconnectAttempts: number = 0
    private reconnectTimer?: NodeJS.Timeout

    // 回调函数
    private onLogLine?: LogLineCallback
    private onError?: ErrorCallback
    private onStatusChange?: StatusCallback

    constructor(options: BackendLogCaptureOptions = {}) {
        this.options = {
            bufferOptions: {
                maxBufferSize: 1024 * 1024, // 1MB
                maxLineLength: 64 * 1024,    // 64KB
                flushTimeout: 1000,          // 1秒
                encoding: 'utf8',
                ...options.bufferOptions
            },
            autoReconnect: options.autoReconnect ?? true,
            reconnectInterval: options.reconnectInterval ?? 2000,
            maxReconnectAttempts: options.maxReconnectAttempts ?? 5,
            enableErrorRecovery: options.enableErrorRecovery ?? true
        }

        this.stdoutBuffer = new LogBuffer(this.options.bufferOptions)
        this.stderrBuffer = new LogBuffer(this.options.bufferOptions)

        this.stats = {
            totalBytesCaptured: 0,
            totalLinesCaptured: 0,
            reconnectCount: 0,
            errorCount: 0,
            bufferStats: {}
        }
    }

    /**
     * 开始捕获日志
     * @param process 要捕获的进程
     */
    startCapture(process: ChildProcessWithoutNullStreams): void {
        if (this.isCapturing) {
            console.warn('日志捕获已在运行中')
            return
        }

        this.process = process
        this.isCapturing = true
        this.stats.captureStartTime = new Date()
        this.reconnectAttempts = 0

        this.setupProcessListeners()
        this.notifyStatusChange(true)

        console.log('开始捕获后端日志')
    }

    /**
     * 停止捕获日志
     */
    stopCapture(): void {
        if (!this.isCapturing) {
            return
        }

        this.isCapturing = false
        this.process = null
        this.stats.lastCaptureTime = new Date()

        // 清理重连定时器
        if (this.reconnectTimer) {
            clearTimeout(this.reconnectTimer)
            this.reconnectTimer = undefined
        }

        // 刷新缓冲区
        this.flushBuffers()

        this.notifyStatusChange(false)
        console.log('停止捕获后端日志')
    }

    /**
     * 设置进程监听器
     */
    private setupProcessListeners(): void {
        if (!this.process) return

        // 设置编码
        this.process.stdout?.setEncoding('utf8')
        this.process.stderr?.setEncoding('utf8')

        // 监听stdout
        this.process.stdout?.on('data', (data: string | Buffer) => {
            this.handleStreamData(data, 'stdout')
        })

        // 监听stderr
        this.process.stderr?.on('data', (data: string | Buffer) => {
            this.handleStreamData(data, 'stderr')
        })

        // 监听进程退出
        this.process.once('exit', (code, signal) => {
            this.handleProcessExit(code, signal)
        })

        // 监听进程错误
        this.process.once('error', (error) => {
            this.handleProcessError(error)
        })

        // 监听流错误
        this.process.stdout?.once('error', (error) => {
            this.handleStreamError(error, 'stdout')
        })

        this.process.stderr?.once('error', (error) => {
            this.handleStreamError(error, 'stderr')
        })
    }

    /**
     * 处理流数据
     */
    private handleStreamData(data: string | Buffer, source: 'stdout' | 'stderr'): void {
        if (!this.isCapturing) return

        try {
            const buffer = source === 'stdout' ? this.stdoutBuffer : this.stderrBuffer
            const lines = buffer.addData(data)

            // 更新统计信息
            const dataLength = typeof data === 'string' ? Buffer.byteLength(data, 'utf8') : data.length
            this.stats.totalBytesCaptured += dataLength
            this.stats.totalLinesCaptured += lines.length

            // 触发回调
            lines.forEach(line => {
                this.onLogLine?.(line, source)
            })

        } catch (error) {
            this.handleError(error instanceof Error ? error : new Error(String(error)))
        }
    }

    /**
     * 处理进程退出
     */
    private handleProcessExit(code: number | null, signal: string | null): void {
        console.log(`后端进程退出: code=${code}, signal=${signal}`)

        // 刷新缓冲区
        this.flushBuffers()

        if (this.options.autoReconnect && this.shouldReconnect()) {
            this.scheduleReconnect()
        } else {
            this.stopCapture()
        }
    }

    /**
     * 处理进程错误
     */
    private handleProcessError(error: Error): void {
        console.error('后端进程错误:', error)
        this.handleError(error)

        if (this.options.autoReconnect && this.shouldReconnect()) {
            this.scheduleReconnect()
        } else {
            this.stopCapture()
        }
    }

    /**
     * 处理流错误
     */
    private handleStreamError(error: Error, stream: 'stdout' | 'stderr'): void {
        console.error(`后端${stream}流错误:`, error)
        this.handleError(error)

        if (!this.options.enableErrorRecovery) {
            this.stopCapture()
        }
    }

    /**
     * 处理一般错误
     */
    private handleError(error: Error): void {
        this.stats.errorCount++
        this.onError?.(error)
    }

    /**
     * 判断是否应该重连
     */
    private shouldReconnect(): boolean {
        return this.reconnectAttempts < this.options.maxReconnectAttempts
    }

    /**
     * 安排重连
     */
    private scheduleReconnect(): void {
        if (this.reconnectTimer) {
            clearTimeout(this.reconnectTimer)
        }

        this.reconnectTimer = setTimeout(() => {
            this.attemptReconnect()
        }, this.options.reconnectInterval)
    }

    /**
     * 尝试重连
     */
    private attemptReconnect(): void {
        this.reconnectAttempts++
        this.stats.reconnectCount++

        console.log(`尝试重连后端进程 (${this.reconnectAttempts}/${this.options.maxReconnectAttempts})`)

        // 这里需要外部提供新的进程实例
        // 实际的重连逻辑需要与BackendService配合
        this.stopCapture()
    }

    /**
     * 刷新缓冲区
     */
    private flushBuffers(): void {
        // 刷新stdout缓冲区
        const stdoutLines = this.stdoutBuffer.flushAll()
        stdoutLines.forEach(line => {
            this.onLogLine?.(line, 'stdout')
        })

        // 刷新stderr缓冲区
        const stderrLines = this.stderrBuffer.flushAll()
        stderrLines.forEach(line => {
            this.onLogLine?.(line, 'stderr')
        })
    }

    /**
     * 通知状态变化
     */
    private notifyStatusChange(isCapturing: boolean): void {
        this.onStatusChange?.(isCapturing)
    }

    /**
     * 设置日志行回调
     */
    setLogLineCallback(callback: LogLineCallback): void {
        this.onLogLine = callback
    }

    /**
     * 设置错误回调
     */
    setErrorCallback(callback: ErrorCallback): void {
        this.onError = callback
    }

    /**
     * 设置状态回调
     */
    setStatusCallback(callback: StatusCallback): void {
        this.onStatusChange = callback
    }

    /**
     * 获取统计信息
     */
    getStats(): LogCaptureStats {
        return {
            ...this.stats,
            bufferStats: {
                stdout: this.stdoutBuffer.getStats(),
                stderr: this.stderrBuffer.getStats()
            }
        }
    }

    /**
     * 重置统计信息
     */
    resetStats(): void {
        this.stats = {
            totalBytesCaptured: 0,
            totalLinesCaptured: 0,
            reconnectCount: 0,
            errorCount: 0,
            bufferStats: {}
        }

        this.stdoutBuffer.resetStats()
        this.stderrBuffer.resetStats()
    }

    /**
     * 更新配置
     */
    updateOptions(options: Partial<BackendLogCaptureOptions>): void {
        this.options = { ...this.options, ...options as Required<BackendLogCaptureOptions> }

        if (options.bufferOptions) {
            this.stdoutBuffer.updateOptions(options.bufferOptions)
            this.stderrBuffer.updateOptions(options.bufferOptions)
        }
    }

    /**
     * 获取缓冲区健康状态
     */
    getBufferHealthStatus(): {
        stdout: any
        stderr: any
    } {
        return {
            stdout: this.stdoutBuffer.getHealthStatus(),
            stderr: this.stderrBuffer.getHealthStatus()
        }
    }

    /**
     * 手动刷新缓冲区
     */
    flushBuffersManually(): string[] {
        const allLines: string[] = []

        // 刷新stdout缓冲区
        const stdoutLines = this.stdoutBuffer.flushAll()
        allLines.push(...stdoutLines)

        // 刷新stderr缓冲区
        const stderrLines = this.stderrBuffer.flushAll()
        allLines.push(...stderrLines)

        return allLines
    }

    /**
     * 检查是否正在捕获
     */
    isActive(): boolean {
        return this.isCapturing
    }

    /**
     * 获取当前进程
     */
    getCurrentProcess(): ChildProcessWithoutNullStreams | null {
        return this.process
    }

    /**
     * 清理资源
     */
    destroy(): void {
        this.stopCapture()

        this.stdoutBuffer.destroy()
        this.stderrBuffer.destroy()

        // 清理回调
        this.onLogLine = undefined
        this.onError = undefined
        this.onStatusChange = undefined

        console.log('BackendLogCapture已销毁')
    }
}