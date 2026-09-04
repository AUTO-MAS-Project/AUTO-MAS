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
import {
  RUNTIME_CLIENT_ERROR_DEFINITIONS,
  RuntimeClient,
  RuntimeRemediation,
  RuntimeRunResult,
  RuntimeSuperviseHandle,
  RuntimeSupervisedLaunchConfig,
  createRuntimeClient,
  formatStartupLogs,
  isRuntimeClientError,
  readRuntimeBaseUrl,
  resolveRuntimeLaunchConfig,
  resolveRuntimeLaunchMode,
} from './runtime'

import { getLogger } from './logger'
import { observeMainOperation, recordMainCount, recordMainDuration } from './sentry'
const logger = getLogger('后端服务')
const BACKEND_UNAVAILABLE_CONFIRMATIONS = 3

// Runtime 链路等待 state:running 的兜底上限。正常情况下 Runtime 自己的健康超时会先给出
// BACKEND_HEALTH_TIMEOUT，这个上限只防止 Runtime 既不就绪也不给终态时把启动流程挂死。
const RUNTIME_READY_TIMEOUT_MS = 180000
// 等待 Runtime 完成关闭的上限，超时由客户端 kill Runtime 进程本身，进程树由其 Job Object 收走。
const RUNTIME_SHUTDOWN_TIMEOUT_MS = 30000
// 启动阶段每路输出只保留最近这么多行：后端每行 DEBUG 日志都会以 log 事件到达，
// 失败界面也只需要尾部；无上限累积会在长驻监督期间把内存吃光。
const RUNTIME_STARTUP_LOG_LINE_LIMIT = 200

/** 尾部保留固定行数的追加：超出上限时丢弃最旧的一行。 */
function pushBoundedLine(lines: string[], message: string, limit: number): void {
  lines.push(message)
  if (lines.length > limit) {
    lines.splice(0, lines.length - limit)
  }
}

// ==================== 类型定义 ====================

export interface BackendStatus {
  isRunning: boolean
  pid?: number
  startTime?: Date
  error?: string
  /**
   * 本次生命周期是否走 Runtime 监督链路。渲染进程据此决定关闭方式：Runtime 链路下
   * 后端只能由 Electron 经 Runtime stdin shutdown 停止，渲染进程不得自己 POST /close。
   */
  runtimeSupervised: boolean
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
  /** Runtime 链路的结构化结果码，供界面决定重试或修复；旧链路不产生。 */
  code?: string
  retryable?: boolean
  remediation?: RuntimeRemediation[]
}

/** 渲染进程实际使用的后端地址。 */
export interface BackendApiEndpoints {
  local: string
  websocket: string
}

/** 由 Runtime 下发的 baseUrl 派生 WebSocket 根地址，不自行假定端口。 */
function deriveWebsocketEndpoint(baseUrl: string): string {
  const url = new URL(baseUrl)
  url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:'
  return url.toString().replace(/\/$/, '')
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
  // Runtime 监督链路的句柄与就绪地址；旧链路下始终为 null。
  private runtimeHandle: RuntimeSuperviseHandle | null = null
  private runtimeBaseUrl: string | null = null

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
    // 灰度开关打开后整条生命周期都走 Runtime 监督链路，绝不与旧链路混用：两条链路的端口、
    // 关闭语义与进程归属都不同，中途回退只会留下无人负责的后端进程。
    const launchConfig = resolveRuntimeLaunchConfig(this.appRoot)
    if (launchConfig.mode !== 'off') {
      return this.startBackendViaRuntime(launchConfig, options)
    }

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

  // ==================== Runtime 监督链路 ====================

  /**
   * 经 `auto-mas-runtime.exe backend supervise` 启动后端。
   *
   * 与旧链路的三点区别：
   * 1. 不注入 `AUTO_MAS_DEV` / `AUTO_MAS_HTTP_PORT`：受监督后端的端口与身份由 Runtime 注入的
   *    `AUTO_MAS_SUPERVISED` 一组变量决定，这里再注入只会互相打架。`AUTO_MAS_ENV=development`
   *    与遥测开关一样由 `createRuntimeClient` 按启动模式统一注入（见 runtimeEnv.ts），只影响
   *    后端的遥测判定；
   * 2. 就绪以 `state:running` 事件为准，而不是解析 stdout 里的 `Uvicorn running`；
   * 3. 后端地址取事件里的 `details.baseUrl`，不按 `resolveHttpPort()` 自行拼装。
   *
   * `development` 模式在 supervise 之前先跑一次 `environment ensure`：`backend supervise` 本身
   * 不下载 uv，Runtime 根目录没种过 uv 时会直接以 `UV_EXEC_FAILED` 失败；`managed` 模式的
   * `bootstrap` 已包含这一步，不重复。
   */
  private async startBackendViaRuntime(
    config: RuntimeSupervisedLaunchConfig,
    options?: BackendStartOptions
  ): Promise<BackendStartResult> {
    if (this.runtimeHandle) {
      logger.info('Runtime 已在监督后端，跳过重复启动')
      return { success: true }
    }

    const runtimePath = config.runtimePath
    if (!runtimePath) {
      // 灰度期一次生命周期只走一条链路，找不到可执行文件时直接失败展示，不回退旧链路。
      const definition = RUNTIME_CLIENT_ERROR_DEFINITIONS.RUNTIME_NOT_FOUND
      const message = `找不到 Runtime 可执行文件，无法以 ${config.mode} 模式启动后端`
      logger.error(message)
      return {
        success: false,
        error: message,
        code: definition.code,
        retryable: definition.retryable,
        remediation: [...definition.remediation],
      }
    }

    logger.info(
      `经 Runtime 启动后端 - 模式: ${config.mode}, Runtime: ${runtimePath}, ` +
        `Runtime 根目录: ${config.appRoot}${config.repo ? `, 源码目录: ${config.repo}` : ''}`
    )

    // 遥测开关（AUTO_MAS_TELEMETRY）与开发标记（AUTO_MAS_ENV）由 createRuntimeClient 统一注入，
    // 见 runtimeEnv.ts；配置从用户数据根 dataRoot 读，development 模式下它不是 --app-root。
    const client = createRuntimeClient({
      runtimePath,
      appRoot: config.appRoot,
      dataRoot: config.dataRoot,
      launchMode: config.mode,
    })

    if (config.mode === 'development') {
      const failure = await this.ensureDevelopmentRuntimeEnvironment(client, config)
      if (failure) return failure
    }

    // 后端 stdout / stderr 由 Runtime 逐行包装成 log 事件转发，这里按流分开累积，
    // 失败时组装成现有失败界面直接展示的整块文本。
    const stdoutLines: string[] = []
    const stderrLines: string[] = []
    let resolveReady: (baseUrl: string) => void = () => undefined
    const ready = new Promise<{ baseUrl: string }>(resolve => {
      resolveReady = baseUrl => resolve({ baseUrl })
    })

    let handle: RuntimeSuperviseHandle
    try {
      handle = await client.supervise({
        mode: config.mode,
        repo: config.repo,
        onLog: event => {
          const lines = event.stream === 'stderr' ? stderrLines : stdoutLines
          pushBoundedLine(lines, event.message, RUNTIME_STARTUP_LOG_LINE_LIMIT)
        },
        onState: event => {
          // 就绪的唯一判据是 backend.run 阶段进入 running 且带 baseUrl；其他阶段即便
          // status 同名也不算，baseUrl 必须取自事件本身而不是自行假定端口。
          if (event.stage !== 'backend.run' || event.status !== 'running') return
          const baseUrl = readRuntimeBaseUrl(event.details)
          if (!baseUrl) {
            logger.warn('Runtime 报告 backend.run running 但未携带 baseUrl，忽略该事件')
            return
          }
          resolveReady(baseUrl)
        },
      })
    } catch (error) {
      // 握手阶段的失败（可执行文件缺失、spawn 被拒、协议不匹配、参数错误）都在这里收敛。
      return this.buildRuntimeStartFailure(error, stdoutLines, stderrLines)
    }

    const timeoutMs = options?.timeout || RUNTIME_READY_TIMEOUT_MS
    let timer: NodeJS.Timeout | undefined
    const timedOut = new Promise<'timeout'>(resolve => {
      timer = setTimeout(() => resolve('timeout'), timeoutMs)
      timer.unref?.()
    })
    const ended = handle.completion.then(
      result => ({ result }),
      (error: unknown) => ({ error })
    )

    let outcome: 'timeout' | { baseUrl: string } | { result: RuntimeRunResult } | { error: unknown }
    try {
      outcome = await Promise.race([ready, ended, timedOut])
    } finally {
      if (timer) clearTimeout(timer)
    }

    if (outcome !== 'timeout' && 'baseUrl' in outcome) {
      this.adoptRuntimeHandle(handle, outcome.baseUrl)
      logger.info(`后端服务启动成功，Runtime PID: ${handle.pid}，后端地址: ${outcome.baseUrl}`)
      return { success: true }
    }

    if (outcome === 'timeout') {
      logger.error(`等待 Runtime 报告后端就绪超过 ${timeoutMs}ms，请求关闭 Runtime`)
      try {
        const settled = await handle.shutdown({ timeoutMs: RUNTIME_SHUTDOWN_TIMEOUT_MS })
        return this.buildRuntimeStartFailure(settled, stdoutLines, stderrLines)
      } catch (error) {
        return this.buildRuntimeStartFailure(error, stdoutLines, stderrLines)
      }
    }

    // 就绪前拿到终态或调用侧异常：后端没起来，按失败展示。
    const reason = 'result' in outcome ? outcome.result : outcome.error
    return this.buildRuntimeStartFailure(reason, stdoutLines, stderrLines)
  }

  /**
   * `development` 模式 supervise 之前的准备：创建仓外的 Runtime 根目录并种好 uv。
   *
   * Runtime 要求 `--app-root` 已存在，且 `backend supervise` 不下载 uv，所以先跑一次
   * `environment ensure`（幂等：uv 已在时只做校验，很快返回；首次会下载，实测约一分钟）。
   * 进度只记日志——development 模式在初始化界面上没有对应的段。失败时按与 supervise 失败
   * 同形的结果返回，界面据 `code` / `remediation` 决定重试或修复。
   *
   * 成功返回 null，失败返回可直接交给界面的启动失败结果。
   */
  private async ensureDevelopmentRuntimeEnvironment(
    client: RuntimeClient,
    config: RuntimeSupervisedLaunchConfig
  ): Promise<BackendStartResult | null> {
    try {
      fs.mkdirSync(config.appRoot, { recursive: true })
    } catch (error) {
      const message = `无法创建 Runtime 根目录 ${config.appRoot}: ${
        error instanceof Error ? error.message : String(error)
      }`
      logger.error(message)
      return { success: false, error: message }
    }

    logger.info('development 模式：supervise 之前先经 environment ensure 准备 uv')
    const stdoutLines: string[] = []
    const stderrLines: string[] = []
    let outcome: RuntimeRunResult
    try {
      outcome = await client.run(['environment', 'ensure'], {
        onProgress: event => logger.info(`Runtime ${event.stage}: ${event.message}`),
        onState: event => logger.info(`Runtime ${event.stage}: ${event.message}`),
        onLog: event => {
          if (event.stream === 'stderr') {
            stderrLines.push(event.message)
            return
          }
          stdoutLines.push(event.message)
        },
      })
    } catch (error) {
      return this.buildRuntimeStartFailure(error, stdoutLines, stderrLines)
    }

    if (!outcome.success) {
      return this.buildRuntimeStartFailure(outcome, stdoutLines, stderrLines)
    }

    logger.info(`uv 已就绪，开始 supervise（environment ensure 用时 ${outcome.durationMs}ms）`)
    return null
  }

  /** 记下监督句柄与后端地址，并在 Runtime 结束时清理状态。 */
  private adoptRuntimeHandle(handle: RuntimeSuperviseHandle, baseUrl: string): void {
    this.runtimeHandle = handle
    this.runtimeBaseUrl = baseUrl
    this.startTime = new Date()
    this.notifyStatusChange()

    const onFinished = (): void => {
      if (this.runtimeHandle !== handle) return
      logger.info('Runtime 监督进程已结束，清理后端运行状态')
      this.clearRuntimeState(handle)
    }
    void handle.completion.then(onFinished, onFinished)
  }

  private clearRuntimeState(handle: RuntimeSuperviseHandle): void {
    if (this.runtimeHandle !== handle) return
    this.runtimeHandle = null
    this.runtimeBaseUrl = null
    this.startTime = null
    this.notifyStatusChange()
  }

  /**
   * 把 Runtime 的失败终态或调用侧异常转成与旧链路同形的启动失败结果。
   *
   * `logs` 保持 `[stdout]…\n\n[stderr]…` 的整块格式，现有失败界面不需要改动；`code` /
   * `retryable` / `remediation` 供界面判断可用操作，界面不解析日志或中文文案。
   */
  private buildRuntimeStartFailure(
    reason: RuntimeRunResult | unknown,
    stdoutLines: string[],
    stderrLines: string[]
  ): BackendStartResult {
    if (isRuntimeClientError(reason)) {
      const logs = this.formatRuntimeStartupLogs(stdoutLines, stderrLines, reason.details.stderr)
      logger.error(`Runtime 调用失败: ${reason.code} ${reason.message}`)
      return {
        success: false,
        error: reason.message,
        logs,
        code: reason.code,
        retryable: reason.retryable,
        remediation: [...reason.remediation],
      }
    }

    if (this.isRuntimeRunResult(reason)) {
      const logs = this.formatRuntimeStartupLogs(stdoutLines, stderrLines, reason.stderr)
      const message = reason.result.message || `后端在就绪前结束（${reason.code}）`
      logger.error(`后端服务启动失败: ${reason.code} ${message}`)
      return {
        success: false,
        error: message,
        logs,
        code: reason.code,
        retryable: reason.result.retryable,
        remediation: [...reason.result.remediation],
      }
    }

    const message = reason instanceof Error ? reason.message : String(reason)
    logger.error(`后端服务启动失败: ${message}`)
    return {
      success: false,
      error: message,
      logs: this.formatRuntimeStartupLogs(stdoutLines, stderrLines),
    }
  }

  private isRuntimeRunResult(value: unknown): value is RuntimeRunResult {
    return typeof value === 'object' && value !== null && 'result' in value && 'code' in value
  }

  /** Runtime 自身的 stderr 诊断并入 `[stderr]` 块，避免后端没起来时失败界面一片空白。 */
  private formatRuntimeStartupLogs(
    stdoutLines: string[],
    stderrLines: string[],
    runtimeStderr?: string
  ): string | undefined {
    const diagnostics = runtimeStderr?.trimEnd()
    const merged = diagnostics ? [...stderrLines, ...diagnostics.split(/\r?\n/)] : stderrLines
    return formatStartupLogs(stdoutLines, merged)
  }

  /**
   * 经 Runtime 停止后端：只向 stdin 发 shutdown，不再 taskkill python。
   *
   * 关闭超时由 `handle.shutdown` 兜底 kill Runtime 进程本身，后端进程树由 Runtime 的
   * Job Object 收走，这里不触碰 processManager 的全局清理。
   */
  private async stopBackendViaRuntime(): Promise<BackendStopResult> {
    const handle = this.runtimeHandle
    if (!handle) {
      logger.info('Runtime 链路未持有监督句柄，无需停止后端')
      return { success: true }
    }

    logger.info(`向 Runtime 发送 shutdown，Runtime PID: ${handle.pid}`)
    try {
      const outcome = await handle.shutdown({ timeoutMs: RUNTIME_SHUTDOWN_TIMEOUT_MS })
      if (!outcome.success) {
        logger.warn(`Runtime 关闭后端报告失败: ${outcome.code} ${outcome.result.message}`)
      } else {
        logger.info('Runtime 已确认后端关闭')
      }
      // completion 兑现即意味着 Runtime 已给出终态且进程已退出，进程树随之清理完毕。
      this.clearRuntimeState(handle)
      return { success: true }
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error)
      this.clearRuntimeState(handle)
      if (this.hasRuntimeProcessExited(error)) {
        // 关闭超时被客户端 kill、或 Runtime 没给终态就退出：进程本身已经不在了，
        // 后端进程树随 Job Object 一并回收，对调用方而言后端已停止，不必再弹「无法安全退出」。
        logger.warn(`Runtime 未给出关闭终态就已退出，按已停止处理: ${errorMsg}`)
        return { success: true }
      }
      logger.error(`Runtime 关闭后端失败: ${errorMsg}`)
      return { success: false, error: errorMsg }
    }
  }

  /**
   * 判断关闭失败是否只是「Runtime 进程已退出但没给终态」。
   *
   * 客户端在收到 close 时才以 RUNTIME_EXITED_UNEXPECTEDLY 收尾，退出码与信号至少有一个
   * 非空；两者都为空说明是进程不响应结束信号后的兜底收敛，进程可能还活着，不能算已停止。
   */
  private hasRuntimeProcessExited(error: unknown): boolean {
    if (!isRuntimeClientError(error) || error.code !== 'RUNTIME_EXITED_UNEXPECTEDLY') {
      return false
    }
    const { exitCode, signal } = error.details
    return (
      (exitCode !== null && exitCode !== undefined) || (signal !== null && signal !== undefined)
    )
  }

  /**
   * 本次生命周期是否走 Runtime 监督链路。
   *
   * 已持有句柄时必然是；尚未启动成功时以灰度开关为准，避免在新链路下误用旧链路的
   * scoped taskkill 清理。
   */
  isRuntimeSupervised(): boolean {
    return this.runtimeHandle !== null || resolveRuntimeLaunchMode(this.appRoot) !== 'off'
  }

  /** Runtime 就绪后下发的后端地址；旧链路或尚未就绪时返回 null，由调用方回退原有端点。 */
  getRuntimeApiEndpoints(): BackendApiEndpoints | null {
    if (!this.runtimeBaseUrl) return null
    return {
      local: this.runtimeBaseUrl,
      websocket: deriveWebsocketEndpoint(this.runtimeBaseUrl),
    }
  }

  /** 后端 HTTP 根地址：Runtime 就绪后以它下发的为准，否则用镜像源服务的端点。 */
  private resolveLocalApiEndpoint(): string {
    return this.runtimeBaseUrl ?? this.mirrorService.getApiEndpoint('local')
  }

  // ==================== 旧链路 ====================

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
    const apiEndpoint = this.resolveLocalApiEndpoint()
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
    if (this.isRuntimeSupervised()) {
      return this.stopBackendViaRuntime()
    }

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
    // Runtime 链路下追踪的是监督进程，后端进程树归 Runtime 管，这里不持有它的 PID。
    if (this.runtimeHandle) {
      return {
        isRunning: true,
        pid: this.runtimeHandle.pid,
        startTime: this.startTime || undefined,
        runtimeSupervised: true,
      }
    }

    const isRunning = this.isTrackedProcessRunning()

    return {
      isRunning,
      pid: this.backendProcess?.pid,
      startTime: this.startTime || undefined,
      runtimeSupervised: this.isRuntimeSupervised(),
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
