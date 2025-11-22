/**
 * 后端服务管理 V2
 * 重构版本 - 只负责后端进程的启动、停止和管理
 * WebSocket连接由前端的useWebSocket模块处理
 */

import * as fs from 'fs'
import * as path from 'path'
import { spawn, ChildProcessWithoutNullStreams } from 'child_process'

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

    constructor(appRoot: string) {
        this.appRoot = appRoot
    }

    /**
     * 启动后端服务
     * 注意：只负责启动后端进程，不处理WebSocket连接
     * WebSocket连接应该由前端的useWebSocket模块处理
     */
    async startBackend(
        options?: BackendStartOptions
    ): Promise<{ success: boolean; error?: string }> {
        console.log('=== 启动后端服务 ===')

        // 检查是否已经在运行
        if (this.backendProcess && !this.backendProcess.killed) {
            console.log('后端服务已在运行')
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

            console.log(`Python: ${pythonExe}`)
            console.log(`Main.py: ${mainPy}`)
            console.log(`工作目录: ${cwd}`)

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

            console.log(`✅ 后端服务启动成功，PID: ${this.backendProcess.pid}`)

            return { success: true }
        } catch (error) {
            const errorMsg = error instanceof Error ? error.message : String(error)
            console.error('❌ 后端服务启动失败:', errorMsg)

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
     */
    async stopBackend(): Promise<{ success: boolean; error?: string }> {
        console.log('=== 停止后端服务 ===')

        if (!this.backendProcess || this.backendProcess.killed) {
            console.log('后端服务未运行')
            return { success: true }
        }

        return new Promise((resolve) => {
            const pid = this.backendProcess!.pid
            console.log(`正在停止后端服务，PID: ${pid}`)

            // 设置超时强制结束
            const timeout = setTimeout(() => {
                console.warn('停止超时，强制结束进程')
                try {
                    if (this.backendProcess && !this.backendProcess.killed) {
                        if (process.platform === 'win32') {
                            // Windows 使用 taskkill
                            const { exec } = require('child_process')
                            exec(`taskkill /f /t /pid ${pid}`, (error: any) => {
                                if (error) {
                                    console.error('taskkill 失败:', error)
                                }
                            })
                        } else {
                            this.backendProcess.kill('SIGKILL')
                        }
                    }
                } catch (e) {
                    console.error('强制结束失败:', e)
                }
                this.backendProcess = null
                this.startTime = null
                resolve({ success: true })
            }, 2000)

            // 监听进程退出
            this.backendProcess!.once('exit', (code, signal) => {
                clearTimeout(timeout)
                console.log(`后端服务已退出，code: ${code}, signal: ${signal}`)
                this.backendProcess = null
                this.startTime = null
                this.notifyStatusChange()
                resolve({ success: true })
            })

            // 发送终止信号
            try {
                this.backendProcess!.kill('SIGTERM')
                console.log('已发送 SIGTERM 信号')
            } catch (e) {
                clearTimeout(timeout)
                console.error('发送终止信号失败:', e)
                this.backendProcess = null
                this.startTime = null
                resolve({ success: false, error: String(e) })
            }
        })
    }

    /**
     * 重启后端服务
     */
    async restartBackend(
        options?: BackendStartOptions
    ): Promise<{ success: boolean; error?: string }> {
        console.log('=== 重启后端服务 ===')

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

        this.backendProcess.stdout?.on('data', (data: string) => {
            const log = this.stripAnsiColors(data.trim())
            if (log) {
                console.log('[Backend]', log)
                this.logCallback?.(log)
            }
        })

        this.backendProcess.stderr?.on('data', (data: string) => {
            const log = this.stripAnsiColors(data.trim())
            if (log) {
                console.log('[Backend]', log)
                this.logCallback?.(log)
            }
        })

        this.backendProcess.once('exit', (code, signal) => {
            console.log(`后端进程退出，code: ${code}, signal: ${signal}`)
            this.backendProcess = null
            this.startTime = null
            this.notifyStatusChange()
        })

        this.backendProcess.once('error', (error) => {
            console.error('后端进程错误:', error)
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
     * 去除 ANSI 颜色代码
     */
    private stripAnsiColors(str: string): string {
        return str.replace(/\x1b\[[0-9;]*m/g, '')
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
        console.log('=== 清理后端服务资源 ===')
        await this.stopBackend()
    }
}
