/**
 * 后端服务管理
 * 重构版本 - 只负责后端进程的启动、停止和管理
 * WebSocket连接由前端的useWebSocket模块处理
 */

import * as fs from 'fs'
import * as path from 'path'
import { spawn, ChildProcessWithoutNullStreams } from 'child_process'

import { killAllRelatedProcesses } from '../utils/processManager'
import { MirrorService } from './mirrorService'

import { getLogger } from './logger'
const logger = getLogger('后端服务')

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

export type BackendStatusCallback = (status: BackendStatus) => void

// ==================== 后端服务管理类 ====================

export class BackendService {
    private appRoot: string
    private mirrorService: MirrorService
    private backendProcess: ChildProcessWithoutNullStreams | null = null
    private startTime: Date | null = null
    private statusCallback: BackendStatusCallback | null = null

    constructor(appRoot: string, mirrorService: MirrorService) {
        this.appRoot = appRoot
        this.mirrorService = mirrorService
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
            logger.info('后端服务已在运行')
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
            logger.info(`启动后端 - Python: ${pythonExe}, Main.py: ${mainPy}, 工作目录: ${cwd}`)

            // 启动后端进程
            this.backendProcess = spawn(pythonExe, [mainPy], {
                cwd,
                stdio: ['pipe', 'pipe', 'pipe'],
                env: { ...process.env, PYTHONIOENCODING: 'utf-8' },
            })

            this.startTime = new Date()

            // 设置输出监听
            this.setupProcessListeners()

            // 等待后端启动
            await this.waitForBackendReady(timeout)

            logger.info(`后端服务启动成功，PID: ${this.backendProcess.pid}`)

            return { success: true }
        } catch (error) {
            const errorMsg = error instanceof Error ? error.message : String(error)
            logger.error(`后端服务启动失败: ${errorMsg}`)

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
            logger.info(`停止后端服务，PID: ${pid}`)
        } else {
            logger.info('尝试停止后端服务（未追踪到进程，可能是外部启动的）')
        }

        // 第一步：尝试通过 API 优雅关闭（无论是否追踪到进程）
        let apiSuccess = false
        try {
            // 从 MirrorService 获取 API 端点
            const apiEndpoint = this.mirrorService.getApiEndpoint('local')
            const apiUrl = `${apiEndpoint}/api/core/close`

            logger.info(`尝试通过 ${apiUrl} 接口关闭后端`)
            const controller = new AbortController()
            const apiTimeout = setTimeout(() => controller.abort(), 5000) // 增加到5秒

            const response = await fetch(apiUrl, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                signal: controller.signal,
                redirect: 'follow' // 允许重定向
            })
            clearTimeout(apiTimeout)

            if (response.ok) {
                logger.info('API 关闭请求发送成功，等待后端退出')
                apiSuccess = true
            } else {
                logger.warn(`API 关闭请求返回错误: ${response.status}`)
            }
        } catch (e: any) {
            // API 调用失败（可能后端已经崩溃或网络不可达）
            const errorMsg = e instanceof Error ? `${e.name}: ${e.message}` : String(e)
            logger.warn(`API 关闭请求失败: ${errorMsg}`)

            // 检查具体错误类型
            if (e?.cause?.code === 'ECONNREFUSED') {
                logger.warn('连接被拒绝，后端可能未运行或已关闭')
            } else if (e instanceof Error && e.name === 'AbortError') {
                logger.warn('API 请求超时，后端可能无响应')
            } else if (e?.cause) {
                logger.warn(`底层错误: ${e.cause.code || e.cause.message || e.cause}`)
            }
        }

        // 如果没有追踪到进程
        if (!hasTrackedProcess) {
            if (apiSuccess) {
                // API 成功，等待一段时间让后端退出
                await new Promise(resolve => setTimeout(resolve, 2000))
                logger.info('后端服务应该已经关闭')
            } else {
                // API 失败，尝试强制清理
                logger.info('API 调用失败，尝试强制清理相关进程')
                await killAllRelatedProcesses()
            }
            return { success: true }
        }

        // 第二步：等待进程自行退出，或超时后强制结束
        return new Promise((resolve) => {
            // 设置超时强制结束（5秒，给后端足够时间清理）
            const timeout = setTimeout(async () => {
                logger.warn('等待后端退出超时，强制清理所有相关进程')
                await killAllRelatedProcesses()
                this.backendProcess = null
                this.startTime = null
                resolve({ success: true })
            }, 2000)

            // 监听进程退出
            if (this.backendProcess) {
                this.backendProcess.once('exit', (code, signal) => {
                    clearTimeout(timeout)
                    logger.info(`后端服务已退出，code: ${code}, signal: ${signal}`)
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
        logger.info('重启后端服务')

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
            logger.info(`后端进程退出，code: ${code}, signal: ${signal}`)
            this.backendProcess = null
            this.startTime = null
            this.notifyStatusChange()
        })

        this.backendProcess.once('error', (error) => {
            logger.error(`后端进程错误: ${error}`)
            this.notifyStatusChange()
        })
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
     * 清理资源
     */
    async cleanup(): Promise<void> {
        logger.info('清理后端服务资源')

        // 停止后端服务
        await this.stopBackend()
    }
}
