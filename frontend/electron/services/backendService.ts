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
import { isDevelopmentEnvironment } from './environmentService'
import { resolveHttpPort } from './instanceConfig'

import { getLogger } from './logger'
import { observeMainOperation, recordMainCount, recordMainDuration } from './sentry'
const logger = getLogger('后端服务')
const BACKEND_UNAVAILABLE_CONFIRMATIONS = 3

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

export interface BackendStartResult {
  success: boolean
  error?: string
  logs?: string
}

export interface BackendStopResult {
  success: boolean
  error?: string
}

export type BackendStatusCallback = (status: BackendStatus) => void

// ==================== 后端服务管理类 ====================

export class BackendService {
  private appRoot: string
  private mirrorService: MirrorService
  private backendProcess: ChildProcessWithoutNullStreams | null = null
  private startTime: Date | null = null
  private statusCallback: BackendStatusCallback | null = null
  private startupStdout = ''
  private startupStderr = ''
  private isCapturingStartupLogs = false
  // 进程变更统一进入同一串行队列；同类重复调用共享在途 Promise。
  // restart 在一个队列单元内直接调用内部 stop/start，避免公共方法二次入队造成自锁。
  private operationTail: Promise<void> = Promise.resolve()
  private startFlight: Promise<BackendStartResult> | null = null
  private stopFlight: Promise<BackendStopResult> | null = null
  private restartFlight: Promise<BackendStartResult> | null = null
  private forceStopFlight: Promise<BackendStopResult> | null = null
  private forceStopRequested = false
  private lastKnownBackendDevMode: boolean | null = null

  private readonly startupHealthPath = '/api/core/health'

  constructor(appRoot: string, mirrorService: MirrorService) {
    this.appRoot = appRoot
    this.mirrorService = mirrorService
  }

  private enqueueOperation<T>(operation: () => Promise<T>): Promise<T> {
    const result = this.operationTail.then(operation, operation)
    this.operationTail = result.then(
      () => undefined,
      () => undefined
    )
    return result
  }

  /**
   * 启动后端服务
   * 注意：只负责启动后端进程，不处理WebSocket连接
   * WebSocket连接应该由前端的useWebSocket模块处理
   */
  startBackend(options?: BackendStartOptions): Promise<BackendStartResult> {
    if (this.startFlight) return this.startFlight
    const operation = this.enqueueOperation(() => this.startBackendInternal(options))
    this.startFlight = operation
    void operation.then(
      () => {
        if (this.startFlight === operation) this.startFlight = null
      },
      () => {
        if (this.startFlight === operation) this.startFlight = null
      }
    )
    return operation
  }

  private async startBackendInternal(options?: BackendStartOptions): Promise<BackendStartResult> {
    const startedAt = performance.now()

    return observeMainOperation(
      'AUTO-MAS backend startup',
      'auto_mas.backend.start',
      { component: 'electron-main' },
      async () => {
        const result = await this.startBackendProcess(options)
        const attributes = {
          component: 'electron-main',
          outcome: result.success ? 'success' : 'failure',
        }

        recordMainCount('auto_mas.backend.starts', attributes)
        recordMainDuration(
          'auto_mas.backend.startup.duration',
          performance.now() - startedAt,
          attributes
        )
        return result
      }
    )
  }

  private async startBackendProcess(options?: BackendStartOptions): Promise<BackendStartResult> {
    // 检查是否已经在运行
    if (this.isTrackedProcessRunning()) {
      logger.info('后端服务已在运行，等待健康检查')
      try {
        await this.waitUntilReady(options?.timeout || 60000)
        return { success: true }
      } catch (error) {
        const errorMsg = error instanceof Error ? error.message : String(error)
        return { success: false, error: errorMsg }
      }
    }

    this.resetStartupLogs()

    try {
      const shouldStartNewBackend = await this.prepareUntrackedBackendForStart()
      if (!shouldStartNewBackend) {
        return { success: true }
      }
      if (this.forceStopRequested) {
        throw new Error('强制停止已请求，取消启动后端')
      }

      const pythonExe =
        options?.pythonPath || path.join(this.appRoot, 'environment', 'python', 'python.exe')
      const mainPy = options?.mainPyPath || path.join(this.appRoot, 'main.py')
      const cwd = options?.cwd || this.appRoot
      const timeout = options?.timeout || 60000

      // 检查文件是否存在
      if (!fs.existsSync(pythonExe)) {
        throw new Error(`Python 可执行文件不存在: ${pythonExe}`)
      }
      if (!fs.existsSync(mainPy)) {
        throw new Error(`后端主文件不存在: ${mainPy}`)
      }

      // 合并关键信息到一行日志
      logger.info(`启动后端 - Python: ${pythonExe}, Main.py: ${mainPy}, 工作目录: ${cwd}`)

      this.isCapturingStartupLogs = true

      // 启动后端进程
      this.backendProcess = spawn(pythonExe, [mainPy], {
        cwd,
        stdio: ['pipe', 'pipe', 'pipe'],
        env: this.createBackendEnvironment(),
      })

      this.startTime = new Date()

      // 设置输出监听
      this.setupProcessListeners()

      // 等待后端健康接口可用
      await this.waitUntilReady(timeout)

      logger.info(`后端服务启动成功，PID: ${this.backendProcess.pid}`)
      this.resetStartupLogs()

      return { success: true }
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error)
      const startupLogs = this.formatStartupLogs()
      logger.error(`后端服务启动失败: ${errorMsg}`)

      // force-stop 已在同一队列中等待时，由它唯一负责 scoped taskkill；
      // start 此处不能先清理一次，否则会对同一组 PID 重复执行强杀。
      if (this.forceStopRequested) {
        this.resetStartupLogs()
        return { success: false, error: errorMsg, logs: startupLogs }
      }

      // 启动失败后必须等待 scoped taskkill 确认退出；仅发送 kill 信号就清引用，
      // 会让旧 child 的延迟 exit 事件干扰下一次 start。
      const failedProcess = this.backendProcess
      if (failedProcess) {
        try {
          await killAllRelatedProcesses(this.appRoot)
          if (this.backendProcess === failedProcess) {
            this.resetTrackedProcess()
          } else {
            this.resetStartupLogs()
          }
        } catch (cleanupError) {
          const cleanupMessage =
            cleanupError instanceof Error ? cleanupError.message : String(cleanupError)
          logger.error(`启动失败后的后端清理未确认完成: ${cleanupMessage}`)
          this.resetStartupLogs()
        }
      } else {
        this.resetStartupLogs()
      }

      return { success: false, error: errorMsg, logs: startupLogs }
    }
  }

  private async prepareUntrackedBackendForStart(): Promise<boolean> {
    const apiEndpoint = this.mirrorService.getApiEndpoint('local')
    const metaUrl = `${apiEndpoint}/api/core/ws_meta`
    const closeUrl = `${apiEndpoint}/api/core/close`

    try {
      logger.info(`启动前检查旧后端: ${metaUrl}`)
      const metaResponse = await this.fetchWithTimeout(metaUrl, { method: 'GET' }, 3000)
      if (!metaResponse.ok) {
        return true
      }

      const meta = (await metaResponse.json()) as { devMode?: boolean }
      if (typeof meta.devMode === 'boolean') {
        this.lastKnownBackendDevMode = meta.devMode
      }
      if (meta.devMode) {
        logger.info('检测到开发模式旧后端，复用现有后端进程')
        return false
      }
    } catch (error) {
      const errorMsg = error instanceof Error ? `${error.name}: ${error.message}` : String(error)
      logger.debug(`启动前未发现旧后端: ${errorMsg}`)
      return true
    }

    logger.info(`检测到生产模式旧后端，尝试通过 ${closeUrl} 关闭`)
    const closeResponse = await this.fetchWithTimeout(
      closeUrl,
      {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
      },
      5000
    )
    if (!closeResponse.ok) {
      throw new Error(`旧后端关闭请求返回错误: ${closeResponse.status}`)
    }

    const closed = await this.waitForBackendUnavailable(metaUrl, 5000)
    if (!closed) {
      throw new Error('旧后端关闭超时，取消启动新后端以避免端口冲突')
    }
    return true
  }

  /**
   * 读取后端权威开发模式；暂时不可达时回退最近一次成功结果。
   */
  async getBackendDevMode(): Promise<boolean | null> {
    const apiEndpoint = this.mirrorService.getApiEndpoint('local')
    const metaUrl = `${apiEndpoint}/api/core/ws_meta`

    try {
      const response = await this.fetchWithTimeout(metaUrl, { method: 'GET' }, 1000)
      if (!response.ok) return this.lastKnownBackendDevMode

      const meta = (await response.json()) as { devMode?: boolean }
      if (typeof meta.devMode !== 'boolean') return this.lastKnownBackendDevMode

      this.lastKnownBackendDevMode = meta.devMode
      return meta.devMode
    } catch (error) {
      const errorMsg = error instanceof Error ? `${error.name}: ${error.message}` : String(error)
      logger.debug(`读取后端开发模式失败，使用最近结果: ${errorMsg}`)
      return this.lastKnownBackendDevMode
    }
  }

  private async fetchWithTimeout(
    url: string,
    init: RequestInit,
    timeoutMs: number
  ): Promise<Response> {
    const controller = new AbortController()
    const timeout = setTimeout(() => controller.abort(), timeoutMs)

    try {
      return await fetch(url, {
        ...init,
        signal: controller.signal,
      })
    } finally {
      clearTimeout(timeout)
    }
  }

  private async waitForBackendUnavailable(metaUrl: string, timeoutMs: number): Promise<boolean> {
    const startedAt = Date.now()
    let unavailableCount = 0

    while (Date.now() - startedAt < timeoutMs) {
      try {
        await this.fetchWithTimeout(metaUrl, { method: 'GET' }, 1000)
        // 任意 HTTP 响应都证明监听端仍可达，包括启动或关闭过程中的非 2xx。
        unavailableCount = 0
      } catch {
        unavailableCount += 1
        if (unavailableCount >= BACKEND_UNAVAILABLE_CONFIRMATIONS) return true
      }
      await new Promise(resolve => setTimeout(resolve, 500))
    }
    return false
  }

  /**
   * 停止后端服务
   * 通过调用 /api/core/close 接口优雅关闭后端
   */
  stopBackend(): Promise<BackendStopResult> {
    if (this.stopFlight) return this.stopFlight
    const operation = this.enqueueOperation(() => this.stopBackendInternal())
    this.stopFlight = operation
    void operation.then(
      () => {
        if (this.stopFlight === operation) this.stopFlight = null
      },
      () => {
        if (this.stopFlight === operation) this.stopFlight = null
      }
    )
    return operation
  }

  private async stopBackendInternal(): Promise<BackendStopResult> {
    const pid = this.backendProcess?.pid
    const hasTrackedProcess = this.isTrackedProcessRunning()
    let metaUrl: string | null = null

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
      metaUrl = `${apiEndpoint}/api/core/ws_meta`
      const apiUrl = `${apiEndpoint}/api/core/close`

      logger.info(`尝试通过 ${apiUrl} 接口关闭后端`)
      const response = await this.fetchWithTimeout(
        apiUrl,
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          redirect: 'follow',
        },
        5000
      )

      if (response.ok) {
        logger.info('API 关闭请求发送成功，等待后端退出')
        apiSuccess = true
      } else {
        logger.warn(`API 关闭请求返回错误: ${response.status}`)
      }
    } catch (e: unknown) {
      // API 调用失败（可能后端已经崩溃或网络不可达）
      const errorMsg = e instanceof Error ? `${e.name}: ${e.message}` : String(e)
      logger.warn(`API 关闭请求失败: ${errorMsg}`)

      // 检查具体错误类型
      const cause =
        e instanceof Error
          ? (e as Error & { cause?: { code?: string; message?: string } }).cause
          : undefined
      if (cause?.code === 'ECONNREFUSED') {
        logger.warn('连接被拒绝，后端可能未运行或已关闭')
      } else if (e instanceof Error && e.name === 'AbortError') {
        logger.warn('API 请求超时，后端可能无响应')
      } else if (cause) {
        logger.warn(`底层错误: ${cause.code || cause.message || String(cause)}`)
      }
    }

    // 如果没有追踪到进程
    if (!hasTrackedProcess) {
      if (apiSuccess && metaUrl) {
        const closed = await this.waitForBackendUnavailable(metaUrl, 5000)
        if (closed) {
          logger.info('已确认未追踪后端退出')
          return { success: true }
        }
        logger.warn('API 已响应，但未追踪后端仍可访问，转入强制清理')
      } else {
        logger.info('API 调用失败，转入强制清理相关进程')
      }
      try {
        await killAllRelatedProcesses(this.appRoot)
        return { success: true }
      } catch (error) {
        const errorMsg = error instanceof Error ? error.message : String(error)
        return { success: false, error: errorMsg }
      }
    }

    // 第二步：等待进程自行退出，或超时后强制结束
    const trackedProcess = this.backendProcess
    return new Promise(resolve => {
      let settled = false
      let timeout: NodeJS.Timeout | null = null
      const finish = (result: BackendStopResult): void => {
        if (settled) return
        settled = true
        if (timeout) clearTimeout(timeout)
        resolve(result)
      }

      // 设置超时强制结束（5秒，给后端足够时间清理）
      timeout = setTimeout(() => {
        void (async () => {
          logger.warn('等待后端退出超时，强制清理所有相关进程')
          try {
            await killAllRelatedProcesses(this.appRoot)
            if (this.backendProcess === trackedProcess) {
              this.backendProcess = null
              this.startTime = null
              this.notifyStatusChange()
            }
            finish({ success: true })
          } catch (error) {
            const errorMsg = error instanceof Error ? error.message : String(error)
            logger.error(`等待退出超时后的强制清理失败: ${errorMsg}`)
            finish({ success: false, error: errorMsg })
          }
        })()
      }, 5000)

      // 监听进程退出
      if (trackedProcess) {
        trackedProcess.once('exit', (code, signal) => {
          logger.info(`后端服务已退出，code: ${code}, signal: ${signal}`)
          if (this.backendProcess === trackedProcess) {
            this.backendProcess = null
            this.startTime = null
            this.notifyStatusChange()
          }
          finish({ success: true })
        })
      } else {
        finish({ success: true })
      }
    })
  }

  /**
   * 重启后端服务
   */
  restartBackend(options?: BackendStartOptions): Promise<BackendStartResult> {
    if (this.restartFlight) return this.restartFlight
    const operation = this.enqueueOperation(async () => {
      if (this.forceStopRequested) {
        return { success: false, error: '强制停止已请求，取消后端重启' }
      }
      logger.info('重启后端服务')
      const stopResult = await this.stopBackendInternal()
      if (!stopResult.success) return stopResult
      if (this.forceStopRequested) {
        return { success: false, error: '强制停止已请求，取消后端重启' }
      }
      await new Promise(resolve => setTimeout(resolve, 1000))
      if (this.forceStopRequested) {
        return { success: false, error: '强制停止已请求，取消后端重启' }
      }
      return this.startBackendInternal(options)
    })
    this.restartFlight = operation
    void operation.then(
      () => {
        if (this.restartFlight === operation) this.restartFlight = null
      },
      () => {
        if (this.restartFlight === operation) this.restartFlight = null
      }
    )
    return operation
  }

  /**
   * 强制结束相关进程。与 start/stop/restart 共用串行队列，保证 taskkill
   * 永远不会和后端重启并发执行。
   */
  forceStopBackend(): Promise<BackendStopResult> {
    this.forceStopRequested = true
    if (this.forceStopFlight) return this.forceStopFlight
    const operation = this.enqueueOperation(async () => {
      logger.warn('强制结束后端相关进程')
      try {
        await killAllRelatedProcesses(this.appRoot)
        this.backendProcess = null
        this.startTime = null
        this.notifyStatusChange()
        return { success: true }
      } catch (error) {
        const errorMsg = error instanceof Error ? error.message : String(error)
        logger.error(`强制结束后端相关进程失败: ${errorMsg}`)
        return { success: false, error: errorMsg }
      }
    })
    this.forceStopFlight = operation
    void operation.then(
      () => {
        if (this.forceStopFlight === operation) {
          this.forceStopFlight = null
          this.forceStopRequested = false
        }
      },
      () => {
        if (this.forceStopFlight === operation) {
          this.forceStopFlight = null
          this.forceStopRequested = false
        }
      }
    )
    return operation
  }

  async waitUntilReady(timeoutMs: number = 60000): Promise<void> {
    const healthUrl = `${this.mirrorService.getApiEndpoint('local')}${this.startupHealthPath}`
    const startedAt = Date.now()

    while (Date.now() - startedAt < timeoutMs) {
      if (this.forceStopRequested) {
        throw new Error('强制停止已请求，取消等待后端启动')
      }
      if (this.backendProcess && !this.isTrackedProcessRunning()) {
        throw new Error('后端进程已退出')
      }

      try {
        const response = await this.fetchWithTimeout(healthUrl, { method: 'GET' }, 1000)
        if (response.ok) {
          const health = (await response.json()) as { ready?: boolean }
          if (health.ready) {
            return
          }
        }
      } catch {
        // 后端尚未监听，继续等待。
      }

      if (this.forceStopRequested) {
        throw new Error('强制停止已请求，取消等待后端启动')
      }
      await new Promise(resolve => setTimeout(resolve, 100))
    }

    throw new Error('等待后端健康检查超时')
  }

  /**
   * 获取后端状态
   */
  getStatus(): BackendStatus {
    const isRunning = this.isTrackedProcessRunning()

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
    const process = this.backendProcess

    process.stdout?.setEncoding('utf8')
    process.stderr?.setEncoding('utf8')

    process.stdout?.on('data', data => {
      this.captureStartupOutput('stdout', data)
    })

    process.stderr?.on('data', data => {
      this.captureStartupOutput('stderr', data)
    })

    process.once('exit', (code, signal) => {
      logger.info(`后端进程退出，code: ${code}, signal: ${signal}`)
      if (this.backendProcess === process) {
        this.backendProcess = null
        this.startTime = null
        this.notifyStatusChange()
      }
    })

    process.once('error', error => {
      logger.error(`后端进程错误: ${error}`)
      if (this.backendProcess === process) this.notifyStatusChange()
    })
  }

  private isTrackedProcessRunning(): boolean {
    return Boolean(
      this.backendProcess?.pid &&
      !this.backendProcess.killed &&
      this.backendProcess.exitCode === null
    )
  }

  private resetTrackedProcess(): void {
    this.backendProcess = null
    this.startTime = null
    this.resetStartupLogs()
    this.notifyStatusChange()
  }

  private captureStartupOutput(stream: 'stdout' | 'stderr', data: Buffer | string): void {
    if (!this.isCapturingStartupLogs) return

    const output = data.toString()

    if (stream === 'stdout') {
      this.startupStdout += output
      return
    }

    this.startupStderr += output
  }

  private formatStartupLogs(): string | undefined {
    const sections: string[] = []
    const stdout = this.startupStdout.trimEnd()
    const stderr = this.startupStderr.trimEnd()

    if (stdout) {
      sections.push(`[stdout]\n${stdout}`)
    }

    if (stderr) {
      sections.push(`[stderr]\n${stderr}`)
    }

    return sections.length > 0 ? sections.join('\n\n') : undefined
  }

  private resetStartupLogs(): void {
    this.startupStdout = ''
    this.startupStderr = ''
    this.isCapturingStartupLogs = false
  }

  /**
   * 通知状态变化
   */
  private createBackendEnvironment(): NodeJS.ProcessEnv {
    const env: NodeJS.ProcessEnv = { ...process.env }
    const inheritedPath = process.env.PATH || process.env.Path

    for (const key of Object.keys(env)) {
      if (key.toLowerCase() === 'path') {
        delete env[key]
      }
    }

    if (inheritedPath !== undefined) {
      env[process.platform === 'win32' ? 'Path' : 'PATH'] = inheritedPath
    }
    env.PYTHONIOENCODING = 'utf-8'
    // 由前端拉起的后端无需自行提权
    env.AUTO_MAS_DEV = '1'
    // 与前端使用的端点对齐，避免后端按自身环境判定另选端口
    env.AUTO_MAS_HTTP_PORT = String(resolveHttpPort())
    // 仅开发环境标记运行环境，打包版必须清除继承值以正常上报遥测
    if (isDevelopmentEnvironment()) {
      env.AUTO_MAS_ENV = 'development'
    } else {
      delete env.AUTO_MAS_ENV
    }
    return env
  }

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
