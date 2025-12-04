/**
 * 后端服务管理
 * 重构版本 - 只负责后端进程的启动、停止和管理
 * WebSocket连接由前端的useWebSocket模块处理
 */

import * as fs from 'fs'
import * as path from 'path'
import { spawn, ChildProcessWithoutNullStreams } from 'child_process'

import { logService } from './logService'
import { killAllRelatedProcesses } from '../utils/processManager'
// 导入新的日志处理组件
import { LoguruBackendLogParser } from '../utils/loguruBackendLogParser'
import { BackendLogCapture } from '../utils/backendLogCapture'
import { LogStreamProcessor } from '../utils/logStreamProcessor'
import { LogSource } from '../types/log'

// ==================== 类型定义 ====================

export interface BackendStatus {
    isRunning: boolean
    pid?: number
    startTime?: Date
    error?: string
}

export interface BackendStartOptions {
    pythonPath?: string
    mainPyPath?: string
    cwd?: string
    timeout?: number // 启动超时时间（毫秒）
}

export type BackendLogCallback = (log: string) => void
export type BackendStatusCallback = (status: BackendStatus) => void

// ==================== 后端服务管理类 ====================

export class BackendService {
    private appRoot: string
    private backendProcess: ChildProcessWithoutNullStreams | null = null
    private startTime: Date | null = null
    private logCallback: BackendLogCallback | null = null
    private statusCallback: BackendStatusCallback | null = null

    // 新的日志处理组件
    private logParser: LoguruBackendLogParser
    private logCapture: BackendLogCapture | null = null
    private logProcessor: LogStreamProcessor | null = null
    private logCaptureEnabled: boolean = true

    constructor(appRoot: string) {
        this.appRoot = appRoot

        // 初始化新的日志处理组件
        this.logParser = LoguruBackendLogParser.getInstance()
        this.initializeLogProcessing()
    }

    /**
     * 初始化日志处理组件
     */
    private initializeLogProcessing(): void {
        // 创建日志流处理器
        this.logProcessor = new LogStreamProcessor({
            batchSize: 50,
            batchTimeout: 300,
            maxQueueSize: 5000,
            enableBackpressure: true,
            enablePriority: true,
            enableAsync: true,
            maxConcurrency: 3
        })

        // 设置日志处理回调
        // 由于我们已经修改了logStreamProcessor直接调用前端日志方法，这里不再需要额外的处理
        // 避免重复处理日志
        this.logProcessor.setProcessedLogCallback((logEntry) => {
            // 不再调用handleProcessedLog，避免重复处理
            // 日志已经在logStreamProcessor中通过FrontendLogAdapter处理了
        })

        this.logProcessor.setErrorCallback((error, logLine) => {
            logService.error('后端日志处理', `处理失败: ${error.message}`)
            if (logLine) {
                logService.error('后端日志处理', `失败日志行: ${logLine.substring(0, 100)}`)
            }
        })
    }

    /**
     * 启动后端服务
     * 注意：只负责启动后端进程，不处理WebSocket连接
     * WebSocket连接应该由前端的useWebSocket模块处理
     */
    async startBackend(
        options?: BackendStartOptions
    ): Promise<{ success: boolean; error?: string }> {
        // 检查是否已经在运行
        if (this.backendProcess && !this.backendProcess.killed) {
            logService.info('后端服务', '后端服务已在运行')
            return { success: true }
        }

        try {
            const pythonExe =
                options?.pythonPath || path.join(this.appRoot, 'environment', 'python', 'python.exe')
            const mainPy = options?.mainPyPath || path.join(this.appRoot, 'main.py')
            const cwd = options?.cwd || this.appRoot
            const timeout = options?.timeout || 30000

            // 检查文件是否存在
            if (!fs.existsSync(pythonExe)) {
                throw new Error(`Python 可执行文件不存在: ${pythonExe}`)
            }
            if (!fs.existsSync(mainPy)) {
                throw new Error(`后端主文件不存在: ${mainPy}`)
            }

            // 合并关键信息到一行日志
            logService.info('后端服务', `启动后端 - Python: ${pythonExe}, Main.py: ${mainPy}, 工作目录: ${cwd}`)

            // 启动后端进程
            this.backendProcess = spawn(pythonExe, [mainPy], {
                cwd,
                stdio: ['pipe', 'pipe', 'pipe'],
                env: { ...process.env, PYTHONIOENCODING: 'utf-8' },
            })

            this.startTime = new Date()

            // 设置输出监听
            this.setupProcessListeners()

            // 启动日志捕获
            if (this.logCaptureEnabled) {
                this.startLogCapture()
            }

            // 等待后端启动
            await this.waitForBackendReady(timeout)

            logService.info('后端服务', `后端服务启动成功，PID: ${this.backendProcess.pid}`)

            return { success: true }
        } catch (error) {
            const errorMsg = error instanceof Error ? error.message : String(error)
            logService.error('后端服务', `后端服务启动失败: ${errorMsg}`)

            // 清理进程
            if (this.backendProcess) {
                this.backendProcess.kill()
                this.backendProcess = null
            }

            return { success: false, error: errorMsg }
        }
    }

    /**
     * 停止后端服务
     * 通过调用 /api/core/close 接口优雅关闭后端
     */
    async stopBackend(): Promise<{ success: boolean; error?: string }> {
        const pid = this.backendProcess?.pid
        const hasTrackedProcess = this.backendProcess && !this.backendProcess.killed

        if (hasTrackedProcess) {
            logService.info('后端服务', `停止后端服务，PID: ${pid}`)
        } else {
            logService.info('后端服务', '尝试停止后端服务（未追踪到进程，可能是外部启动的）')
        }

        // 第一步：尝试通过 API 优雅关闭（无论是否追踪到进程）
        let apiSuccess = false
        try {
            logService.info('后端服务', '尝试通过 /api/core/close 接口关闭后端')
            const controller = new AbortController()
            const apiTimeout = setTimeout(() => controller.abort(), 5000) // 增加到5秒

            const response = await fetch('http://localhost:36163/api/core/close', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                signal: controller.signal
            })
            clearTimeout(apiTimeout)

            if (response.ok) {
                logService.info('后端服务', 'API 关闭请求发送成功，等待后端退出')
                apiSuccess = true
            } else {
                logService.warn('后端服务', `API 关闭请求返回错误: ${response.status}`)
            }
        } catch (e: any) {
            // API 调用失败（可能后端已经崩溃或网络不可达）
            const errorMsg = e instanceof Error ? `${e.name}: ${e.message}` : String(e)
            logService.warn('后端服务', `API 关闭请求失败: ${errorMsg}`)

            // 检查具体错误类型
            if (e?.cause?.code === 'ECONNREFUSED') {
                logService.warn('后端服务', '连接被拒绝，后端可能未运行或已关闭')
            } else if (e instanceof Error && e.name === 'AbortError') {
                logService.warn('后端服务', 'API 请求超时，后端可能无响应')
            } else if (e?.cause) {
                logService.warn('后端服务', `底层错误: ${e.cause.code || e.cause.message || e.cause}`)
            }
        }

        // 如果没有追踪到进程
        if (!hasTrackedProcess) {
            if (apiSuccess) {
                // API 成功，等待一段时间让后端退出
                await new Promise(resolve => setTimeout(resolve, 2000))
                logService.info('后端服务', '后端服务应该已经关闭')
            } else {
                // API 失败，尝试强制清理
                logService.info('后端服务', 'API 调用失败，尝试强制清理相关进程')
                await killAllRelatedProcesses()
            }
            return { success: true }
        }

        // 第二步：等待进程自行退出，或超时后强制结束
        return new Promise((resolve) => {
            // 设置超时强制结束（5秒，给后端足够时间清理）
            const timeout = setTimeout(async () => {
                logService.warn('后端服务', '等待后端退出超时，强制清理所有相关进程')
                await killAllRelatedProcesses()
                this.backendProcess = null
                this.startTime = null
                resolve({ success: true })
            }, 2000)

            // 监听进程退出
            if (this.backendProcess) {
                this.backendProcess.once('exit', (code, signal) => {
                    clearTimeout(timeout)
                    logService.info('后端服务', `后端服务已退出，code: ${code}, signal: ${signal}`)
                    this.backendProcess = null
                    this.startTime = null
                    this.notifyStatusChange()
                    resolve({ success: true })
                })
            } else {
                clearTimeout(timeout)
                resolve({ success: true })
            }
        })
    }

    /**
     * 重启后端服务
     */
    async restartBackend(
        options?: BackendStartOptions
    ): Promise<{ success: boolean; error?: string }> {
        logService.info('后端服务', '重启后端服务')

        // 先停止
        const stopResult = await this.stopBackend()
        if (!stopResult.success) {
            return stopResult
        }

        // 等待一小段时间
        await new Promise((resolve) => setTimeout(resolve, 1000))

        // 再启动
        return await this.startBackend(options)
    }

    /**
     * 获取后端状态
     */
    getStatus(): BackendStatus {
        const isRunning = this.backendProcess !== null && !this.backendProcess.killed

        return {
            isRunning,
            pid: this.backendProcess?.pid,
            startTime: this.startTime || undefined,
        }
    }

    /**
     * 设置日志回调
     */
    setLogCallback(callback: BackendLogCallback): void {
        this.logCallback = callback
    }

    /**
     * 启用/禁用日志捕获
     */
    setLogCaptureEnabled(enabled: boolean): void {
        this.logCaptureEnabled = enabled

        if (enabled && this.backendProcess && !this.logCapture) {
            this.startLogCapture()
        } else if (!enabled && this.logCapture) {
            this.stopLogCapture()
        }
    }

    /**
     * 获取日志捕获状态
     */
    getLogCaptureStatus(): {
        enabled: boolean
        active: boolean
        stats?: any
    } {
        return {
            enabled: this.logCaptureEnabled,
            active: this.logCapture?.isActive() || false,
            stats: this.logCapture?.getStats()
        }
    }

    /**
     * 设置状态回调
     */
    setStatusCallback(callback: BackendStatusCallback): void {
        this.statusCallback = callback
    }

    /**
     * 设置进程监听器
     */
    private setupProcessListeners(): void {
        if (!this.backendProcess) return

        this.backendProcess.stdout?.setEncoding('utf8')
        this.backendProcess.stderr?.setEncoding('utf8')

        this.backendProcess.once('exit', (code, signal) => {
            logService.info('后端服务', `后端进程退出，code: ${code}, signal: ${signal}`)
            this.stopLogCapture()
            this.backendProcess = null
            this.startTime = null
            this.notifyStatusChange()
        })

        this.backendProcess.once('error', (error) => {
            logService.error('后端服务', `后端进程错误: ${error}`)
            this.stopLogCapture()
            this.notifyStatusChange()
        })
    }

    /**
     * 启动日志捕获
     */
    private startLogCapture(): void {
        if (!this.backendProcess || !this.logCaptureEnabled) return

        this.logCapture = new BackendLogCapture({
            autoReconnect: false, // 进程重连由BackendService管理
            enableErrorRecovery: true
        })

        // 设置日志行回调
        this.logCapture.setLogLineCallback((line, source) => {
            this.logProcessor?.addLogLine(line, source)
        })

        // 设置错误回调
        this.logCapture.setErrorCallback((error) => {
            logService.error('后端日志捕获', error.message)
        })

        // 开始捕获
        this.logCapture.startCapture(this.backendProcess)
        logService.info('后端服务', '已启动日志捕获')
    }

    /**
     * 停止日志捕获
     */
    private stopLogCapture(): void {
        if (this.logCapture) {
            this.logCapture.stopCapture()
            this.logCapture = null
            logService.info('后端服务', '已停止日志捕获')
        }
    }

    /**
     * 处理处理后的日志条目
     * 已禁用，避免重复处理
     */
    private handleProcessedLog(logEntry: any): void {
        // 不再处理，避免重复
        // 日志已经在logStreamProcessor中通过FrontendLogAdapter处理了
    }

    /**
     * 格式化日志条目
     * 已禁用，避免重复处理
     */
    private formatLogEntry(logEntry: any): string {
        // 不再格式化，避免重复
        return ""
    }

    /**
     * 等待后端就绪
     */
    private waitForBackendReady(timeout: number): Promise<void> {
        return new Promise((resolve, reject) => {
            let settled = false
            const timer = setTimeout(() => {
                if (!settled) {
                    settled = true
                    reject(new Error('后端启动超时'))
                }
            }, timeout)

            const checkReady = (data: Buffer | string) => {
                if (settled) return
                const output = data.toString()

                // 检查 Uvicorn 启动标志
                if (/Uvicorn running|http:\/\/0\.0\.0\.0:\d+/.test(output)) {
                    settled = true
                    clearTimeout(timer)
                    resolve()
                }
            }

            this.backendProcess!.stdout?.on('data', checkReady)
            this.backendProcess!.stderr?.on('data', checkReady)

            this.backendProcess!.once('exit', (code, signal) => {
                if (!settled) {
                    settled = true
                    clearTimeout(timer)
                    reject(new Error(`后端提前退出: code=${code}, signal=${signal}`))
                }
            })

            this.backendProcess!.once('error', (error) => {
                if (!settled) {
                    settled = true
                    clearTimeout(timer)
                    reject(error)
                }
            })
        })
    }


    /**
     * 通知状态变化
     */
    private notifyStatusChange(): void {
        if (this.statusCallback) {
            this.statusCallback(this.getStatus())
        }
    }

    /**
     * 获取日志处理统计信息
     */
    getLogProcessingStats(): any {
        return {
            parser: this.logParser.getStats(),
            processor: this.logProcessor?.getStats(),
            capture: this.logCapture?.getStats()
        }
    }

    /**
     * 更新日志处理配置
     */
    updateLogProcessingConfig(config: any): void {
        if (this.logProcessor && config.processor) {
            this.logProcessor.updateOptions(config.processor)
        }

        if (this.logCapture && config.capture) {
            this.logCapture.updateOptions(config.capture)
        }

        if (config.parser) {
            if (config.parser.cacheEnabled !== undefined) {
                this.logParser.setCacheEnabled(config.parser.cacheEnabled)
            }
            if (config.parser.maxCacheSize !== undefined) {
                this.logParser.setMaxCacheSize(config.parser.maxCacheSize)
            }
        }
    }

    /**
     * 刷新日志处理管道
     */
    async flushLogPipeline(): Promise<void> {
        if (this.logProcessor) {
            await this.logProcessor.flush()
        }

        if (this.logCapture) {
            this.logCapture.flushBuffersManually()
        }
    }

    /**
     * 清理资源
     */
    async cleanup(): Promise<void> {
        logService.info('后端服务', '清理后端服务资源')

        // 停止日志捕获
        this.stopLogCapture()

        // 刷新日志处理管道
        await this.flushLogPipeline()

        // 销毁日志处理器
        if (this.logProcessor) {
            await this.logProcessor.destroy()
            this.logProcessor = null
        }

        // 停止后端服务
        await this.stopBackend()
    }
}
