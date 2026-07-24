/**
 * 后端服务管理
 * 重构版本 - 只负责后端进程的启动、停止和管理
 * WebSocket连接由前端的useWebSocket模块处理
 */

import * as crypto from 'crypto'
import * as fs from 'fs'
import * as path from 'path'
import { spawn, ChildProcessWithoutNullStreams } from 'child_process'

import { MirrorService } from './mirrorService'
import { writeJsonFileAtomically } from './atomicJsonFile'
import {
  getBundledRuntimeReleaseEnvironment,
  requiresBundledRuntimeLock,
} from './bundledRuntimePolicy'

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

export interface BackendRuntimeMutationResult {
  success: boolean
  wasRunning: boolean
  error?: string
}

export interface BackendManagedProcessInfo {
  pid: number
  name: string
  command: string
  commandLine: string
}

interface BackendProcessIdentity {
  pid: number
  creationTime: string
  executablePath: string
  commandLine: string
}

interface BackendOwnershipMarker extends BackendProcessIdentity {
  schemaVersion: 1
  appRoot: string
  mainPy: string
  ownerToken: string
  createdAt: string
}

interface BackendEndpointProbe {
  reachable: boolean
  valid: boolean
  devMode?: boolean
  ownerToken?: string
  httpAuthToken?: string
  pid?: number
}

interface BackendSpawnEnvironmentOptions {
  uvDir: string
  processPath: string
  processPathExt: string
  ownerToken: string | null
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
  private backendOwnerToken: string | null = null
  private backendOwnerPid: number | null = null
  private readonly ownershipMarkerPath: string
  private lifecycleGate: Promise<void> = Promise.resolve()

  // ---- 预热相关 ----
  private _isPrewarming = false
  private readonly startupHealthPath = '/api/core/health'

  constructor(appRoot: string, mirrorService: MirrorService) {
    this.appRoot = appRoot
    this.mirrorService = mirrorService
    this.ownershipMarkerPath = path.join(appRoot, 'environment', '.backend_ownership.json')
  }

  /**
   * 启动后端服务
   * 注意：只负责启动后端进程，不处理WebSocket连接
   * WebSocket连接应该由前端的useWebSocket模块处理
   */
  async startBackend(options?: BackendStartOptions): Promise<BackendStartResult> {
    return await this.runLifecycleOperation(() => this.startBackendUnlocked(options))
  }

  private async startBackendUnlocked(options?: BackendStartOptions): Promise<BackendStartResult> {
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
      const shouldStartNewBackend = await this.prepareUntrackedBackendForStart(options)
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
      const ownerToken = this.createBackendOwnerToken(options)

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
      const launchedProcess = spawn(pythonExe, this.getBackendPythonArgs(mainPy), {
        cwd,
        stdio: ['pipe', 'pipe', 'pipe'],
        env: this.getBackendSpawnEnvironment({
          uvDir,
          processPath,
          processPathExt,
          ownerToken,
        }),
      })
      this.backendProcess = launchedProcess

      this.startTime = new Date()
      this.setupProcessListeners(launchedProcess)

      if (ownerToken && launchedProcess.pid) {
        this.backendOwnerToken = ownerToken
        this.backendOwnerPid = launchedProcess.pid
        const markerWritten = await this.recordBackendOwnership(
          launchedProcess.pid,
          ownerToken,
          pythonExe,
          mainPy
        )
        if (!markerWritten) {
          logger.warn('无法记录后端进程归属信息；本次进程仍可由当前窗口安全停止')
        }
      }

      // 等待后端健康接口可用
      await this.waitUntilReady(timeout, launchedProcess)

      const readyPid = await this.verifyReadyBackendProcess(launchedProcess, ownerToken)
      logger.info(`后端服务启动成功，PID: ${readyPid}`)
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

  private async prepareUntrackedBackendForStart(options?: BackendStartOptions): Promise<boolean> {
    const probe = await this.probeBackendEndpoint()
    if (probe.reachable && probe.valid && probe.devMode) {
      if (this.isDevelopmentOrCustomLaunch(options)) {
        logger.info('检测到开发模式旧后端，复用现有后端进程')
        return false
      }
      throw new Error(
        '端口 36163 正被开发模式 AUTO-MAS 占用；发布版不会复用或停止该后端，请关闭后重试。'
      )
    }

    const stopResult = await this.stopBackendForRuntimeMutationUnlocked()
    if (!stopResult.success) {
      throw new Error(stopResult.error || '旧后端无法安全停止')
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
   * 在更新运行时文件前，仅停止能够证明属于当前安装目录的生产后端。
   */
  async stopBackendForRuntimeMutation(): Promise<BackendRuntimeMutationResult> {
    return await this.runLifecycleOperation(() => this.stopBackendForRuntimeMutationUnlocked())
  }

  private async stopBackendForRuntimeMutationUnlocked(): Promise<BackendRuntimeMutationResult> {
    if (this.isTrackedProcessRunning()) {
      return await this.stopTrackedBackendForRuntimeMutation()
    }

    let ownership: BackendOwnershipMarker | null
    try {
      ownership = await this.loadVerifiedBackendOwnership()
    } catch (error) {
      return {
        success: false,
        wasRunning: false,
        error: `后端归属校验失败，已拒绝修改运行时文件: ${error instanceof Error ? error.message : String(error)}`,
      }
    }

    const probe = await this.probeBackendEndpoint()
    if (probe.reachable && probe.valid && probe.devMode) {
      return {
        success: false,
        wasRunning: true,
        error: '检测到开发模式后端，已拒绝停止或修改其运行时文件',
      }
    }

    if (probe.reachable) {
      if (!probe.valid || !ownership || !this.probeMatchesOwnership(probe, ownership)) {
        return {
          success: false,
          wasRunning: true,
          error: '检测到无法确认属于当前安装目录的后端，已拒绝停止或修改运行时文件',
        }
      }

      const closeResult = await this.requestBackendClose(probe.httpAuthToken)
      if (closeResult.success) {
        const exited = await this.waitForOwnedProcessExit(ownership, 5000)
        if (exited) {
          this.clearOwnershipMarker(ownership.pid, ownership.ownerToken)
          return { success: true, wasRunning: true }
        }
      }
    }

    if (ownership) {
      const terminated = await this.terminateOwnedProcess(ownership)
      if (!terminated) {
        return {
          success: false,
          wasRunning: true,
          error: '属于当前安装目录的后端无法安全停止，已取消运行时更新',
        }
      }
      this.clearOwnershipMarker(ownership.pid, ownership.ownerToken)
      return { success: true, wasRunning: true }
    }

    return { success: true, wasRunning: false }
  }

  private async stopTrackedBackendForRuntimeMutation(): Promise<BackendRuntimeMutationResult> {
    const trackedProcess = this.backendProcess
    const pid = trackedProcess?.pid
    const ownerToken = this.backendOwnerToken
    if (!trackedProcess || !pid) {
      return { success: true, wasRunning: false }
    }
    if (!ownerToken) {
      return {
        success: false,
        wasRunning: true,
        error: '当前后端属于开发或自定义启动，已拒绝自动停止并修改运行时文件',
      }
    }

    const probe = await this.probeBackendEndpoint()
    if (probe.reachable && probe.valid && probe.devMode) {
      return {
        success: false,
        wasRunning: true,
        error: '检测到开发模式后端，已拒绝停止或修改其运行时文件',
      }
    }

    if (probe.reachable && this.probeMatchesTrackedProcess(probe, pid, ownerToken)) {
      const closeResult = await this.requestBackendClose(probe.httpAuthToken)
      if (closeResult.success && (await this.waitForTrackedProcessExit(trackedProcess, 5000))) {
        this.clearOwnershipMarker(pid, ownerToken)
        return { success: true, wasRunning: true }
      }
    }

    try {
      trackedProcess.kill()
    } catch (error) {
      logger.warn(`精确终止当前后端失败: ${error}`)
    }
    if (!(await this.waitForTrackedProcessExit(trackedProcess, 3000))) {
      return {
        success: false,
        wasRunning: true,
        error: `当前后端 PID ${pid} 无法安全停止，已取消运行时更新`,
      }
    }

    this.clearOwnershipMarker(pid, ownerToken)
    return { success: true, wasRunning: true }
  }

  private async probeBackendEndpoint(): Promise<BackendEndpointProbe> {
    const metaUrl = `${this.mirrorService.getApiEndpoint('local')}/api/core/ws_meta`
    try {
      const response = await this.fetchWithTimeout(metaUrl, { method: 'GET' }, 3000)
      if (!response.ok) {
        return { reachable: true, valid: false }
      }

      const meta = (await response.json()) as { devMode?: unknown; wsAuthToken?: unknown }
      if (typeof meta.devMode !== 'boolean') {
        return { reachable: true, valid: false }
      }

      const pidText = response.headers.get('x-auto-mas-owner-pid') || ''
      const pid = Number.parseInt(pidText, 10)
      return {
        reachable: true,
        valid: true,
        devMode: meta.devMode,
        ownerToken: response.headers.get('x-auto-mas-owner-token') || undefined,
        httpAuthToken:
          typeof meta.wsAuthToken === 'string' && meta.wsAuthToken.length >= 32
            ? meta.wsAuthToken
            : undefined,
        pid: Number.isSafeInteger(pid) && pid > 0 ? pid : undefined,
      }
    } catch (error) {
      const errorMsg = error instanceof Error ? `${error.name}: ${error.message}` : String(error)
      logger.debug(`未检测到可访问的后端元信息接口: ${errorMsg}`)
      return { reachable: false, valid: false }
    }
  }

  async getBackendAuthToken(): Promise<string> {
    const probe = await this.probeBackendEndpoint()
    if (!probe.reachable || !probe.valid || !probe.httpAuthToken) {
      throw new Error('Unable to obtain the local backend authentication token')
    }
    return probe.httpAuthToken
  }

  private async requestBackendClose(
    authToken?: string
  ): Promise<{ success: boolean; error?: string }> {
    const closeUrl = `${this.mirrorService.getApiEndpoint('local')}/api/core/close`
    try {
      const token = authToken || (await this.getBackendAuthToken())
      const response = await this.fetchWithTimeout(
        closeUrl,
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'X-AUTO-MAS-Auth-Token': token,
          },
        },
        5000
      )
      if (!response.ok) {
        return { success: false, error: `后端关闭请求返回错误: ${response.status}` }
      }
      return { success: true }
    } catch (error) {
      return { success: false, error: error instanceof Error ? error.message : String(error) }
    }
  }

  private probeMatchesOwnership(
    probe: BackendEndpointProbe,
    ownership: BackendOwnershipMarker
  ): boolean {
    return probe.pid === ownership.pid && probe.ownerToken === ownership.ownerToken
  }

  private probeMatchesTrackedProcess(
    probe: BackendEndpointProbe,
    pid: number,
    ownerToken: string
  ): boolean {
    return probe.pid === pid && probe.ownerToken === ownerToken
  }

  private isDevelopmentOrCustomLaunch(options?: BackendStartOptions): boolean {
    if (requiresBundledRuntimeLock(this.appRoot)) return false
    const isDevelopment =
      process.env.NODE_ENV === 'development' ||
      ['1', 'true', 'yes', 'on'].includes(String(process.env.AUTO_MAS_DEV || '').toLowerCase())
    return Boolean(isDevelopment || options?.pythonPath || options?.mainPyPath || options?.cwd)
  }

  private createBackendOwnerToken(options?: BackendStartOptions): string | null {
    return this.isDevelopmentOrCustomLaunch(options) ? null : crypto.randomUUID()
  }

  private async recordBackendOwnership(
    pid: number,
    ownerToken: string,
    pythonExe: string,
    mainPy: string
  ): Promise<boolean> {
    try {
      const identity = await this.inspectProcessIdentity(pid)
      if (
        !identity ||
        this.normalizeFilesystemPath(identity.executablePath) !==
          this.normalizeFilesystemPath(pythonExe) ||
        !this.commandLineContainsPath(identity.commandLine, mainPy)
      ) {
        return false
      }
      if (
        this.backendOwnerPid !== pid ||
        this.backendOwnerToken !== ownerToken ||
        !this.isTrackedProcessRunning()
      ) {
        return false
      }

      const marker: BackendOwnershipMarker = {
        schemaVersion: 1,
        appRoot: path.resolve(this.appRoot),
        mainPy: path.resolve(mainPy),
        ownerToken,
        createdAt: new Date().toISOString(),
        ...identity,
      }
      writeJsonFileAtomically(this.ownershipMarkerPath, marker)
      return true
    } catch (error) {
      logger.warn(`写入后端归属标记失败: ${error}`)
      return false
    }
  }

  private async loadVerifiedBackendOwnership(): Promise<BackendOwnershipMarker | null> {
    if (!fs.existsSync(this.ownershipMarkerPath)) {
      return null
    }

    let marker: BackendOwnershipMarker
    try {
      const content = fs.readFileSync(this.ownershipMarkerPath, 'utf-8').replace(/^\uFEFF/, '')
      marker = JSON.parse(content) as BackendOwnershipMarker
    } catch (error) {
      this.quarantineOwnershipMarker('unreadable')
      logger.warn(`归属标记无法读取，已隔离: ${error}`)
      return null
    }

    if (
      marker.schemaVersion !== 1 ||
      !Number.isSafeInteger(marker.pid) ||
      marker.pid <= 0 ||
      typeof marker.creationTime !== 'string' ||
      typeof marker.commandLine !== 'string' ||
      typeof marker.executablePath !== 'string' ||
      typeof marker.appRoot !== 'string' ||
      typeof marker.mainPy !== 'string' ||
      typeof marker.ownerToken !== 'string' ||
      marker.ownerToken.length < 16 ||
      this.normalizeFilesystemPath(marker.appRoot) !== this.normalizeFilesystemPath(this.appRoot) ||
      this.normalizeFilesystemPath(marker.mainPy) !==
        this.normalizeFilesystemPath(path.join(this.appRoot, 'main.py')) ||
      this.normalizeFilesystemPath(marker.executablePath) !==
        this.normalizeFilesystemPath(path.join(this.appRoot, '.venv', 'Scripts', 'python.exe'))
    ) {
      this.quarantineOwnershipMarker('invalid')
      logger.warn('归属标记不属于当前安装目录或格式无效，已隔离')
      return null
    }

    const identity = await this.inspectProcessIdentity(marker.pid)
    if (!identity) {
      this.clearOwnershipMarker(marker.pid, marker.ownerToken)
      return null
    }
    if (
      identity.creationTime !== marker.creationTime ||
      this.normalizeFilesystemPath(identity.executablePath) !==
        this.normalizeFilesystemPath(marker.executablePath) ||
      identity.commandLine.trim() !== marker.commandLine.trim() ||
      !this.commandLineContainsPath(identity.commandLine, marker.mainPy)
    ) {
      this.quarantineOwnershipMarker('stale')
      logger.warn(`PID ${marker.pid} 已被其他进程复用或命令行不匹配，归属标记已隔离`)
      return null
    }

    return marker
  }

  private inspectProcessIdentity(pid: number): Promise<BackendProcessIdentity | null> {
    if (process.platform !== 'win32') {
      return Promise.resolve(null)
    }

    return new Promise((resolve, reject) => {
      const script = [
        "$ErrorActionPreference = 'Stop'",
        "$ProgressPreference = 'SilentlyContinue'",
        '[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)',
        `$processInfo = Get-CimInstance Win32_Process -Filter 'ProcessId = ${pid}'`,
        'if ($null -eq $processInfo) { exit 3 }',
        "$creationTime = $processInfo.CreationDate.ToUniversalTime().ToString('o')",
        '[pscustomobject]@{ pid = [int]$processInfo.ProcessId; creationTime = $creationTime; executablePath = [string]$processInfo.ExecutablePath; commandLine = [string]$processInfo.CommandLine } | ConvertTo-Json -Compress',
      ].join('; ')
      const proc = spawn(
        'powershell.exe',
        ['-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-Command', script],
        { stdio: 'pipe', windowsHide: true }
      )
      let stdout = ''
      let stderr = ''
      let settled = false
      const finish = (callback: () => void) => {
        if (settled) return
        settled = true
        clearTimeout(timeout)
        callback()
      }
      const timeout = setTimeout(() => {
        proc.kill()
        finish(() => reject(new Error(`查询 PID ${pid} 进程信息超时`)))
      }, 5000)

      proc.stdout.on('data', data => {
        stdout += data.toString()
      })
      proc.stderr.on('data', data => {
        stderr += data.toString()
      })
      proc.once('error', error => finish(() => reject(error)))
      proc.once('close', code => {
        if (code === 3) {
          finish(() => resolve(null))
          return
        }
        if (code !== 0) {
          finish(() => reject(new Error(stderr.trim() || `查询 PID ${pid} 失败: ${code}`)))
          return
        }
        try {
          const parsed = JSON.parse(stdout.trim()) as BackendProcessIdentity
          if (
            parsed.pid !== pid ||
            typeof parsed.creationTime !== 'string' ||
            typeof parsed.executablePath !== 'string' ||
            typeof parsed.commandLine !== 'string'
          ) {
            finish(() => reject(new Error(`PID ${pid} 进程信息字段无效`)))
            return
          }
          finish(() => resolve(parsed))
        } catch (error) {
          finish(() => reject(new Error(`解析 PID ${pid} 进程信息失败: ${error}`)))
        }
      })
    })
  }

  private async terminateOwnedProcess(marker: BackendOwnershipMarker): Promise<boolean> {
    const identity = await this.inspectProcessIdentity(marker.pid)
    if (!identity) {
      return true
    }
    if (
      identity.creationTime !== marker.creationTime ||
      identity.commandLine.trim() !== marker.commandLine.trim() ||
      this.normalizeFilesystemPath(identity.executablePath) !==
        this.normalizeFilesystemPath(marker.executablePath)
    ) {
      return false
    }

    try {
      process.kill(marker.pid)
    } catch (error) {
      logger.warn(`精确终止归属后端 PID ${marker.pid} 失败: ${error}`)
      return false
    }
    return await this.waitForOwnedProcessExit(marker, 3000)
  }

  private async waitForOwnedProcessExit(
    marker: BackendOwnershipMarker,
    timeoutMs: number
  ): Promise<boolean> {
    const startedAt = Date.now()
    while (Date.now() - startedAt < timeoutMs) {
      const identity = await this.inspectProcessIdentity(marker.pid)
      if (!identity || identity.creationTime !== marker.creationTime) {
        return true
      }
      await new Promise(resolve => setTimeout(resolve, 250))
    }
    return false
  }

  private async waitForTrackedProcessExit(
    trackedProcess: ChildProcessWithoutNullStreams,
    timeoutMs: number
  ): Promise<boolean> {
    const startedAt = Date.now()
    while (Date.now() - startedAt < timeoutMs) {
      if (trackedProcess.exitCode !== null || trackedProcess.signalCode !== null) {
        return true
      }
      await new Promise(resolve => setTimeout(resolve, 100))
    }
    return false
  }

  private clearOwnershipMarker(pid: number, ownerToken: string): void {
    try {
      if (!fs.existsSync(this.ownershipMarkerPath)) {
        return
      }
      const marker = JSON.parse(
        fs.readFileSync(this.ownershipMarkerPath, 'utf-8').replace(/^\uFEFF/, '')
      ) as Partial<BackendOwnershipMarker>
      if (marker.pid === pid && marker.ownerToken === ownerToken) {
        fs.rmSync(this.ownershipMarkerPath, { force: true })
      }
    } catch (error) {
      logger.warn(`清理后端归属标记失败: ${error}`)
    }
  }

  private commandLineContainsPath(commandLine: string, targetPath: string): boolean {
    const args = Array.from(commandLine.matchAll(/"([^"]*)"|(\S+)/g), match => match[1] || match[2])
    const normalizedTarget = this.normalizeFilesystemPath(targetPath)
    return args.some(argument => {
      try {
        return this.normalizeFilesystemPath(argument) === normalizedTarget
      } catch {
        return false
      }
    })
  }

  private normalizeFilesystemPath(value: string): string {
    return path
      .resolve(String(value || ''))
      .replace(/\//g, '\\')
      .replace(/\\+$/, '')
      .toLowerCase()
  }

  /**
   * 停止后端服务
   * 通过调用 /api/core/close 接口优雅关闭后端
   */
  async stopBackend(): Promise<{ success: boolean; error?: string }> {
    return await this.runLifecycleOperation(() => this.stopBackendUnlocked())
  }

  private quarantineOwnershipMarker(reason: string): void {
    try {
      if (!fs.existsSync(this.ownershipMarkerPath)) {
        return
      }
      const quarantinePath = `${this.ownershipMarkerPath}.${reason}.${Date.now()}.${crypto.randomUUID()}.invalid`
      fs.renameSync(this.ownershipMarkerPath, quarantinePath)
    } catch (error) {
      logger.warn(`隔离无效后端归属标记失败: ${error}`)
    }
  }

  private async stopBackendUnlocked(): Promise<{ success: boolean; error?: string }> {
    const trackedProcess = this.backendProcess
    const pid = trackedProcess?.pid

    if (trackedProcess && pid && this.isTrackedProcessRunning() && !this.backendOwnerToken) {
      logger.info(`精确停止当前 Electron 实例启动的后端，PID: ${pid}`)
      try {
        trackedProcess.kill()
      } catch (error) {
        return { success: false, error: `停止后端 PID ${pid} 失败: ${error}` }
      }
      if (!(await this.waitForTrackedProcessExit(trackedProcess, 3000))) {
        return { success: false, error: `后端 PID ${pid} 未在超时内退出` }
      }
      this.resetTrackedProcess()
      return { success: true }
    }

    const result = await this.stopBackendForRuntimeMutationUnlocked()
    return result.success ? { success: true } : { success: false, error: result.error }
  }

  /**
   * 重启后端服务
   */
  async restartBackend(options?: BackendStartOptions): Promise<BackendStartResult> {
    return await this.runLifecycleOperation(() => this.restartBackendUnlocked(options))
  }

  private async restartBackendUnlocked(options?: BackendStartOptions): Promise<BackendStartResult> {
    logger.info('重启后端服务')

    // 先停止
    const stopResult = await this.stopBackendUnlocked()
    if (!stopResult.success) {
      return stopResult
    }

    // 等待一小段时间
    await new Promise(resolve => setTimeout(resolve, 1000))

    // 再启动
    return await this.startBackendUnlocked(options)
  }

  /**
   * 预热后端：spawn 进程但不等待就绪，让 Python 与前端渲染并行启动。
   * 后续 startBackend() 调用会识别预热进程并等待其就绪。
   */
  async prewarmBackend(options?: BackendStartOptions): Promise<void> {
    await this.runLifecycleOperation(() => this.prewarmBackendUnlocked(options))
  }

  private async prewarmBackendUnlocked(options?: BackendStartOptions): Promise<void> {
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
      const ownerToken = this.createBackendOwnerToken(options)

      if (!fs.existsSync(pythonExe)) {
        throw new Error(`预热失败：Python 不存在: ${pythonExe}`)
      }
      if (!fs.existsSync(mainPy)) {
        throw new Error(`预热失败：main.py 不存在: ${mainPy}`)
      }

      logger.info(`预热后端: Python=${pythonExe}, Main=${mainPy}, CWD=${cwd}`)

      this.isCapturingStartupLogs = true
      this.startTime = new Date()

      const launchedProcess = spawn(pythonExe, this.getBackendPythonArgs(mainPy), {
        cwd,
        stdio: ['pipe', 'pipe', 'pipe'],
        env: this.getBackendSpawnEnvironment({
          uvDir,
          processPath,
          processPathExt,
          ownerToken,
        }),
      })
      this.backendProcess = launchedProcess

      launchedProcess.stdout?.setEncoding('utf8')
      launchedProcess.stderr?.setEncoding('utf8')
      launchedProcess.stdout?.on('data', (data: string) => {
        this.captureStartupOutput('stdout', data)
      })
      launchedProcess.stderr?.on('data', (data: string) => {
        this.captureStartupOutput('stderr', data)
      })

      launchedProcess.once('exit', (code, signal) => {
        logger.info(`预热后端进程退出，code: ${code}, signal: ${signal}`)
        this.resetTrackedProcess(launchedProcess)
      })

      launchedProcess.once('error', error => {
        logger.error(`预热后端进程错误: ${error}`)
        this.resetTrackedProcess(launchedProcess)
      })

      if (ownerToken && launchedProcess.pid) {
        this.backendOwnerToken = ownerToken
        this.backendOwnerPid = launchedProcess.pid
        await this.recordBackendOwnership(launchedProcess.pid, ownerToken, pythonExe, mainPy)
      }

      this.notifyStatusChange()
      void this.waitUntilReady(options?.timeout || 60000, launchedProcess)
        .then(async () => {
          const readyPid = await this.verifyReadyBackendProcess(launchedProcess, ownerToken)
          logger.info(`预热后端健康检查通过，PID: ${readyPid}`)
          this._isPrewarming = false
          this.resetStartupLogs()
          this.notifyStatusChange()
        })
        .catch(error => {
          const errorMsg = error instanceof Error ? error.message : String(error)
          logger.error(`预热后端健康检查失败: ${errorMsg}`)
          if (this.backendProcess === launchedProcess) {
            launchedProcess.kill()
          }
          this.resetTrackedProcess(launchedProcess)
        })
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.error(`预热后端失败: ${errorMsg}`)
      this.resetTrackedProcess()
    }
  }

  async waitUntilReady(
    timeoutMs: number = 60000,
    expectedProcess: ChildProcessWithoutNullStreams | null = this.backendProcess
  ): Promise<void> {
    const healthUrl = `${this.mirrorService.getApiEndpoint('local')}${this.startupHealthPath}`
    const startedAt = Date.now()

    while (Date.now() - startedAt < timeoutMs) {
      if (
        expectedProcess &&
        (expectedProcess.killed || expectedProcess.exitCode !== null || !expectedProcess.pid)
      ) {
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

  private getBackendPythonArgs(mainPy: string): string[] {
    // Isolate the portable runtime from a machine-wide Python installation. Without -I,
    // PYTHONHOME/PYTHONPATH/registry entries can mix incompatible stdlib DLLs into the venv.
    return ['-I', mainPy]
  }

  private getBackendSpawnEnvironment({
    uvDir,
    processPath,
    processPathExt,
    ownerToken,
  }: BackendSpawnEnvironmentOptions): NodeJS.ProcessEnv {
    const bundledRuntime = requiresBundledRuntimeLock(this.appRoot)
    return {
      ...process.env,
      PATH: `${uvDir}${path.delimiter}${processPath}`,
      Path: `${uvDir}${path.delimiter}${processPath}`,
      PATHEXT: processPathExt,
      PYTHONIOENCODING: 'utf-8',
      AUTO_MAS_UV_EXE: path.join(uvDir, 'uv.exe'),
      AUTO_MAS_ENABLE_MCP: '0',
      ...getBundledRuntimeReleaseEnvironment(this.appRoot),
      ...(bundledRuntime ? { AUTO_MAS_DEV: '0', NODE_ENV: 'production' } : {}),
      ...(ownerToken ? { AUTO_MAS_BACKEND_OWNER_TOKEN: ownerToken } : {}),
    }
  }

  private async verifyReadyBackendProcess(
    expectedProcess: ChildProcessWithoutNullStreams,
    ownerToken: string | null
  ): Promise<number> {
    const pid = expectedProcess.pid
    if (
      !pid ||
      this.backendProcess !== expectedProcess ||
      expectedProcess.killed ||
      expectedProcess.exitCode !== null
    ) {
      throw new Error('后端健康检查通过，但已失去对启动进程的精确追踪')
    }

    if (ownerToken) {
      const probe = await this.probeBackendEndpoint()
      if (
        !probe.reachable ||
        !probe.valid ||
        probe.devMode ||
        !this.probeMatchesTrackedProcess(probe, pid, ownerToken)
      ) {
        throw new Error('后端健康端点不属于本次启动的受管进程')
      }
    }

    return pid
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
   * 返回当前实例跟踪或经归属标记完整校验的生产后端。
   * 不扫描系统中的 Python/main.py 进程，也不暴露其他安装或开发后端。
   */
  async getManagedProcesses(): Promise<BackendManagedProcessInfo[]> {
    if (this.isTrackedProcessRunning() && this.backendProcess?.pid) {
      const pid = this.backendProcess.pid
      let commandLine = ''

      if (this.backendOwnerToken) {
        try {
          const ownership = await this.loadVerifiedBackendOwnership()
          if (ownership?.pid === pid && ownership.ownerToken === this.backendOwnerToken) {
            commandLine = ownership.commandLine
          }
        } catch (error) {
          logger.warn(`读取当前后端归属信息失败: ${error}`)
        }
      }

      return [
        {
          pid,
          name: 'python.exe',
          command: commandLine,
          commandLine,
        },
      ]
    }

    try {
      const ownership = await this.loadVerifiedBackendOwnership()
      if (!ownership) {
        return []
      }

      const probe = await this.probeBackendEndpoint()
      if (
        probe.reachable &&
        (!probe.valid || probe.devMode || !this.probeMatchesOwnership(probe, ownership))
      ) {
        return []
      }

      return [
        {
          pid: ownership.pid,
          name: path.basename(ownership.executablePath),
          command: ownership.commandLine,
          commandLine: ownership.commandLine,
        },
      ]
    } catch (error) {
      logger.warn(`读取已验证后端进程失败: ${error}`)
      return []
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
  private setupProcessListeners(trackedProcess: ChildProcessWithoutNullStreams): void {
    if (this.backendProcess !== trackedProcess) return

    trackedProcess.stdout?.setEncoding('utf8')
    trackedProcess.stderr?.setEncoding('utf8')

    trackedProcess.stdout?.on('data', data => {
      this.captureStartupOutput('stdout', data)
    })

    trackedProcess.stderr?.on('data', data => {
      this.captureStartupOutput('stderr', data)
    })

    trackedProcess.once('exit', (code, signal) => {
      logger.info(`后端进程退出，code: ${code}, signal: ${signal}`)
      this.resetTrackedProcess(trackedProcess)
    })

    trackedProcess.once('error', error => {
      logger.error(`后端进程错误: ${error}`)
      this.resetTrackedProcess(trackedProcess)
    })
  }

  private isTrackedProcessRunning(): boolean {
    return Boolean(
      this.backendProcess?.pid &&
      !this.backendProcess.killed &&
      this.backendProcess.exitCode === null
    )
  }

  private resetTrackedProcess(expectedProcess?: ChildProcessWithoutNullStreams): void {
    if (expectedProcess && this.backendProcess !== expectedProcess) {
      return
    }
    const ownerPid = this.backendOwnerPid
    const ownerToken = this.backendOwnerToken
    if (ownerPid && ownerToken) {
      this.clearOwnershipMarker(ownerPid, ownerToken)
    }
    this.backendProcess = null
    this.backendOwnerPid = null
    this.backendOwnerToken = null
    this.startTime = null
    this._isPrewarming = false
    this.resetStartupLogs()
    this.notifyStatusChange()
  }

  private async runLifecycleOperation<T>(operation: () => Promise<T>): Promise<T> {
    const previousGate = this.lifecycleGate
    let releaseGate: (() => void) | undefined
    this.lifecycleGate = new Promise<void>(resolve => {
      releaseGate = resolve
    })

    await previousGate
    try {
      return await operation()
    } finally {
      releaseGate?.()
    }
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
