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

export interface BackendStartResult {
  success: boolean
  error?: string
  logs?: string
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

  // ---- 预热相关 ----
  private _isPrewarming = false
  private readonly startupHealthPath = '/api/core/health'

  constructor(appRoot: string, mirrorService: MirrorService) {
    this.appRoot = appRoot
    this.mirrorService = mirrorService
  }

  /**
   * 启动后端服务
   * 注意：只负责启动后端进程，不处理WebSocket连接
   * WebSocket连接应该由前端的useWebSocket模块处理
   */
  async startBackend(options?: BackendStartOptions): Promise<BackendStartResult> {
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

      const venvPythonExe = path.join(this.appRoot, '.venv', 'Scripts', 'python.exe')
      const portablePythonExe = path.join(this.appRoot, 'environment', 'python', 'python.exe')
      const pythonExe = options?.pythonPath || venvPythonExe
      const mainPy = options?.mainPyPath || path.join(this.appRoot, 'main.py')
      const cwd = options?.cwd || this.appRoot
      const timeout = options?.timeout || 60000
      const uvDir = path.join(this.appRoot, 'environment', 'python', 'Scripts')
      const processPath = process.env.PATH || process.env.Path || ''
      const processPathExt = process.env.PATHEXT || '.COM;.EXE;.BAT;.CMD'

      // 检查文件是否存在
      if (!fs.existsSync(pythonExe)) {
        if (!options?.pythonPath && fs.existsSync(portablePythonExe)) {
          throw new Error(
            `后端虚拟环境不存在: ${pythonExe}。请先完成依赖安装；基础 Python 位于: ${portablePythonExe}`
          )
        }
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
        env: {
          ...process.env,
          PATH: `${uvDir}${path.delimiter}${processPath}`,
          Path: `${uvDir}${path.delimiter}${processPath}`,
          PATHEXT: processPathExt,
          PYTHONIOENCODING: 'utf-8',
          AUTO_MAS_UV_EXE: path.join(uvDir, 'uv.exe'),
        },
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

      // 清理进程
      if (this.backendProcess) {
        this.backendProcess.kill()
      }

      this.resetTrackedProcess()

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

    while (Date.now() - startedAt < timeoutMs) {
      try {
        const response = await this.fetchWithTimeout(metaUrl, { method: 'GET' }, 1000)
        if (!response.ok) {
          return true
        }
      } catch {
        return true
      }
      await new Promise(resolve => setTimeout(resolve, 500))
    }
    return false
  }

  /**
   * 停止后端服务
   * 通过调用 /api/core/close 接口优雅关闭后端
   */
  async stopBackend(): Promise<{ success: boolean; error?: string }> {
    const pid = this.backendProcess?.pid
    const hasTrackedProcess = this.isTrackedProcessRunning()

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
          'Content-Type': 'application/json',
        },
        signal: controller.signal,
        redirect: 'follow', // 允许重定向
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
    return new Promise(resolve => {
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
  async restartBackend(options?: BackendStartOptions): Promise<BackendStartResult> {
    logger.info('重启后端服务')

    // 先停止
    const stopResult = await this.stopBackend()
    if (!stopResult.success) {
      return stopResult
    }

    // 等待一小段时间
    await new Promise(resolve => setTimeout(resolve, 1000))

    // 再启动
    return await this.startBackend(options)
  }

  /**
   * 预热后端：spawn 进程但不等待就绪，让 Python 与前端渲染并行启动。
   * 后续 startBackend() 调用会识别预热进程并等待其就绪。
   */
  async prewarmBackend(options?: BackendStartOptions): Promise<void> {
    if (this.isTrackedProcessRunning()) {
      logger.info('预热跳过：后端进程已存在')
      return
    }
    if (this._isPrewarming) {
      logger.info('预热跳过：已在预热中')
      return
    }

    this._isPrewarming = true
    this.resetStartupLogs()

    try {
      const shouldStartNewBackend = await this.prepareUntrackedBackendForStart()
      if (!shouldStartNewBackend) {
        this._isPrewarming = false
        return
      }

      const venvPythonExe = path.join(this.appRoot, '.venv', 'Scripts', 'python.exe')
      const pythonExe = options?.pythonPath || venvPythonExe
      const mainPy = options?.mainPyPath || path.join(this.appRoot, 'main.py')
      const cwd = options?.cwd || this.appRoot
      const uvDir = path.join(this.appRoot, 'environment', 'python', 'Scripts')
      const processPath = process.env.PATH || process.env.Path || ''
      const processPathExt = process.env.PATHEXT || '.COM;.EXE;.BAT;.CMD'

      if (!fs.existsSync(pythonExe)) {
        throw new Error(`预热失败：Python 不存在: ${pythonExe}`)
      }
      if (!fs.existsSync(mainPy)) {
        throw new Error(`预热失败：main.py 不存在: ${mainPy}`)
      }

      logger.info(`预热后端: Python=${pythonExe}, Main=${mainPy}, CWD=${cwd}`)

      this.isCapturingStartupLogs = true
      this.startTime = new Date()

      this.backendProcess = spawn(pythonExe, [mainPy], {
        cwd,
        stdio: ['pipe', 'pipe', 'pipe'],
        env: {
          ...process.env,
          PATH: `${uvDir}${path.delimiter}${processPath}`,
          Path: `${uvDir}${path.delimiter}${processPath}`,
          PATHEXT: processPathExt,
          PYTHONIOENCODING: 'utf-8',
          AUTO_MAS_UV_EXE: path.join(uvDir, 'uv.exe'),
        },
      })

      this.backendProcess.stdout?.setEncoding('utf8')
      this.backendProcess.stderr?.setEncoding('utf8')
      this.backendProcess.stdout?.on('data', (data: string) => {
        this.captureStartupOutput('stdout', data)
      })
      this.backendProcess.stderr?.on('data', (data: string) => {
        this.captureStartupOutput('stderr', data)
      })

      this.backendProcess.once('exit', (code, signal) => {
        logger.info(`预热后端进程退出，code: ${code}, signal: ${signal}`)
        this.resetTrackedProcess()
      })

      this.backendProcess.once('error', error => {
        logger.error(`预热后端进程错误: ${error}`)
        this.resetTrackedProcess()
      })

      this.notifyStatusChange()
      void this.waitUntilReady(options?.timeout || 60000)
        .then(() => {
          logger.info('预热后端健康检查通过')
          this._isPrewarming = false
          this.resetStartupLogs()
          this.notifyStatusChange()
        })
        .catch(error => {
          const errorMsg = error instanceof Error ? error.message : String(error)
          logger.error(`预热后端健康检查失败: ${errorMsg}`)
          if (this.backendProcess) {
            this.backendProcess.kill()
          }
          this.resetTrackedProcess()
        })
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.error(`预热后端失败: ${errorMsg}`)
      this.resetTrackedProcess()
    }
  }

  async waitUntilReady(timeoutMs: number = 60000): Promise<void> {
    const healthUrl = `${this.mirrorService.getApiEndpoint('local')}${this.startupHealthPath}`
    const startedAt = Date.now()

    while (Date.now() - startedAt < timeoutMs) {
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

    this.backendProcess.stdout?.setEncoding('utf8')
    this.backendProcess.stderr?.setEncoding('utf8')

    this.backendProcess.stdout?.on('data', data => {
      this.captureStartupOutput('stdout', data)
    })

    this.backendProcess.stderr?.on('data', data => {
      this.captureStartupOutput('stderr', data)
    })

    this.backendProcess.once('exit', (code, signal) => {
      logger.info(`后端进程退出，code: ${code}, signal: ${signal}`)
      this.backendProcess = null
      this.startTime = null
      this.notifyStatusChange()
    })

    this.backendProcess.once('error', error => {
      logger.error(`后端进程错误: ${error}`)
      this.resetTrackedProcess()
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
    this._isPrewarming = false
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
