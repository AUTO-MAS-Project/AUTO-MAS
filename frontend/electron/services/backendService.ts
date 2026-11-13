import { beginMainFeature } from './featureAnalytics'
import { getFluxdownInstallEnvironment } from './fluxdownInstallService'
import { captureScheduledWakeupContext, scheduledWakeupBackendReady } from './scheduledWakeup'
/**
 * 后端服务管理
 * 重构版本 - 只负责后端进程的启动、停止和管理
 * WebSocket连接由前端的useWebSocket模块处理
 */

import * as fs from 'fs'
import { resolveHttpPort } from './instanceConfig'

import {
  RUNTIME_CLIENT_ERROR_DEFINITIONS,
  RuntimeClient,
  RuntimeClientErrorDetails,
  RuntimeRemediation,
  RuntimeRunResult,
  RuntimeLogEvent,
  RuntimeSuperviseHandle,
  RuntimeLaunchConfig,
  createRuntimeClient,
  formatStartupLogs,
  isRuntimeClientError,
  readRuntimeBaseUrl,
  resolveRuntimeLaunchConfig,
} from './runtime'
import { resolveRuntimeTargetVersion, toRuntimeVersion } from './runtimeInitializationService'

import { getLogger } from './logger'
import { observeMainOperation, recordMainCount, recordMainDuration } from './sentry'
import { analyticsService, refreshAnalyticsPreference } from './analyticsService'
import { analyticsDuration } from './analyticsPolicy'
import type { AnalyticsRuntimeMode } from '../../src/types/analytics'
const logger = getLogger('后端服务')

// Runtime 链路等待 state:running 的兜底上限。正常情况下 Runtime 自己的健康超时会先给出
// BACKEND_HEALTH_TIMEOUT，这个上限只防止 Runtime 既不就绪也不给终态时把启动流程挂死。
const RUNTIME_READY_TIMEOUT_MS = 180000
// 监督后端统一保留原有 30 秒清理窗口，覆盖旧 off 生产用户迁入 managed 的情况。
const BACKEND_SHUTDOWN_SECONDS = 30
// 另留 5 秒等待 Runtime 收口；超时才结束 Runtime，由其 Job Object 回收进程树。
const RUNTIME_SHUTDOWN_TIMEOUT_MS = 35000
// 启动阶段每路输出只保留最近这么多行：后端每行 DEBUG 日志都会以 log 事件到达，
// 失败界面也只需要尾部；无上限累积会在长驻监督期间把内存吃光。
const RUNTIME_STARTUP_LOG_LINE_LIMIT = 200
const RUNTIME_STARTUP_LOG_CHAR_LIMIT = 64 * 1024

/** 按行数与字符数保留日志尾部，单条超限时复制截断后的内容。 */
function pushBoundedLine(lines: string[], message: string, limit: number): void {
  const bounded =
    message.length > RUNTIME_STARTUP_LOG_CHAR_LIMIT
      ? Buffer.from(message.slice(-RUNTIME_STARTUP_LOG_CHAR_LIMIT), 'utf8').toString('utf8')
      : message
  for (const line of bounded.split(/\r?\n/).slice(-limit)) {
    lines.push(line)
    let size = lines.reduce((total, item) => total + item.length + 1, -1)
    while (lines.length > limit || (size > RUNTIME_STARTUP_LOG_CHAR_LIMIT && lines.length > 1)) {
      size -= lines.shift()!.length + 1
    }
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
  timeout?: number // 启动超时时间（毫秒）
}

export interface BackendStartResult {
  success: boolean
  error?: string
  logs?: string
  /** Runtime 链路的结构化结果码，供界面决定重试或修复。 */
  code?: string
  retryable?: boolean
  remediation?: RuntimeRemediation[]
  /** 调用侧失败保留命令与真实退出证据，供桌面启动编排决定是否恢复。 */
  runtimeFailure?: Pick<RuntimeClientErrorDetails, 'command' | 'processExited'>
}

/** 渲染进程实际使用的后端地址。 */
interface BackendApiEndpoints {
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

interface RuntimeBackendUpdateCheck {
  updateAvailable: boolean
  staged?: boolean
  currentCommit?: string
  remoteCommit?: string
  commitMessage?: string
  error?: string
}

export type BackendStatusCallback = (status: BackendStatus) => void

// ==================== 后端服务管理类 ====================

export class BackendService {
  private startTime: Date | null = null
  private statusCallback: BackendStatusCallback | null = null
  // 进程变更统一进入同一串行队列；同类重复调用共享在途 Promise。
  // restart 在一个队列单元内直接调用内部 stop/start，避免公共方法二次入队造成自锁。
  private operationTail: Promise<void> = Promise.resolve()
  private startFlight: Promise<BackendStartResult> | null = null
  private stopFlight: Promise<BackendStopResult> | null = null
  private restartFlight: Promise<BackendStartResult> | null = null
  private stopRequested = false
  // 本次监督进程的句柄与就绪地址。
  private runtimeHandle: RuntimeSuperviseHandle | null = null
  private runtimeBaseUrl: string | null = null
  private startingRuntimeHandle: RuntimeSuperviseHandle | null = null
  private runtimeStopping = false
  private runtimeUpdateFlight: Promise<RuntimeBackendUpdateCheck> | null = null
  private runtimeUpdateReady: RuntimeBackendUpdateCheck | null = null
  private readonly runtimeClients = new Set<RuntimeClient>()

  private readonly startupHealthPath = '/api/core/health'
  private analyticsRuntimeMode: AnalyticsRuntimeMode = 'unknown'
  constructor(private readonly appRoot: string) {}

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
    if (this.runtimeHandle) {
      logger.info('Runtime 已在监督后端，跳过重复启动')
      return { success: true }
    }
    if (
      this.startingRuntimeHandle ||
      [...this.runtimeClients].some(client => client.hasActiveSessions)
    ) {
      return {
        success: false,
        code: 'RUNTIME_EXITED_UNEXPECTEDLY',
        retryable: false,
        remediation: ['open-log'],
        error: '无法确认上一次 Runtime 进程已退出，请先停止后端后重试。',
      }
    }
    const startedAt = performance.now()
    refreshAnalyticsPreference()
    const context = analyticsService.getContext()
    this.analyticsRuntimeMode = 'unknown'
    const record = (success: boolean) => {
      refreshAnalyticsPreference()
      analyticsService.recordMainEvent(context, {
        name: 'backend_start_finished',
        props: {
          outcome: success ? 'success' : 'failure',
          runtime_mode: this.analyticsRuntimeMode,
          duration_bucket: analyticsDuration(performance.now() - startedAt),
        },
      })
    }

    return observeMainOperation(
      'AUTO-MAS backend startup',
      'auto_mas.backend.start',
      { component: 'electron-main' },
      async () => {
        let result: BackendStartResult
        try {
          result = await this.startBackendProcess(options)
        } catch (error) {
          record(false)
          throw error
        }
        record(result.success)
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
        logger.info(
          `[启动计时] 桌面/Runtime 与后端启动${result.success ? '完成' : '失败'}，阶段 ${(performance.now() - startedAt).toFixed(1)} ms`
        )
        return result
      }
    )
  }
  private async startBackendProcess(options?: BackendStartOptions): Promise<BackendStartResult> {
    const launchConfig = resolveRuntimeLaunchConfig(this.appRoot)
    this.analyticsRuntimeMode = launchConfig.mode
    return this.startBackendViaRuntime(launchConfig, options)
  }

  // ==================== Runtime 监督链路 ====================

  /**
   * 经 `auto-mas-runtime.exe backend supervise` 启动后端。
   *
   * Runtime 负责后端身份与进程生命周期：
   * 1. 不注入 `AUTO_MAS_DEV` / `AUTO_MAS_HTTP_PORT`：受监督后端的端口与身份由 Runtime 注入的
   *    `AUTO_MAS_SUPERVISED` 一组变量决定，这里再注入只会互相打架。`AUTO_MAS_ENV`
   *    与遥测开关由 `createRuntimeClient` 按应用环境统一注入（见 runtimeEnv.ts），
   *    不改变监督器的端口与退出契约；
   * 2. 就绪以 `state:running` 事件为准，而不是解析 stdout 里的 `Uvicorn running`；
   * 3. 后端地址取事件里的 `details.baseUrl`，不按 `resolveHttpPort()` 自行拼装。
   *
   * `development` 模式在 supervise 之前先跑一次 `environment ensure`：`backend supervise` 本身
   * 不下载 uv，Runtime 根目录没种过 uv 时会直接以 `UV_EXEC_FAILED` 失败。managed 每次启动
   * 先 bootstrap，消费已暂存的同分支更新，并在新进程启动前同步依赖。
   */
  private async startBackendViaRuntime(
    config: RuntimeLaunchConfig,
    options?: BackendStartOptions
  ): Promise<BackendStartResult> {
    if (this.stopFlight || this.stopRequested) {
      return { success: false, error: '正在关闭后端，取消启动' }
    }
    this.runtimeStopping = false

    const runtimePath = config.runtimePath
    if (!runtimePath) {
      // 缺失时显式失败，不能启动安装根目录残留的旧后端。
      const definition = RUNTIME_CLIENT_ERROR_DEFINITIONS.RUNTIME_NOT_FOUND
      const message =
        `找不到 Runtime 可执行文件，无法以 ${config.mode} 模式启动后端` +
        (config.mode === 'development'
          ? '；请设置 AUTO_MAS_RUNTIME_EXE 指向 Runtime，并先运行 uv sync --locked 准备 .venv'
          : '')
      logger.error(message)
      return {
        success: false,
        error: message,
        code: definition.code,
        retryable: definition.retryable,
        remediation: [...definition.remediation],
      }
    }

    const port = resolveHttpPort()
    if (port < 1024) {
      return {
        success: false,
        error:
          'Runtime 要求 AUTO_MAS_HTTP_PORT 为 1024–65535；' +
          '请改用此范围内的端口，低端口调试请独立运行后端与 yarn web。',
        code: 'INVALID_ARGUMENT',
        retryable: true,
        remediation: ['retry', 'open-log'],
      }
    }

    logger.info(
      `经 Runtime 启动后端 - 模式: ${config.mode}, Runtime: ${runtimePath}, ` +
        `Runtime 根目录: ${config.appRoot}${config.repo ? `, 源码目录: ${config.repo}` : ''}`
    )

    // 遥测开关（AUTO_MAS_TELEMETRY）与应用环境（AUTO_MAS_ENV）由 createRuntimeClient 统一注入，
    // 见 runtimeEnv.ts；配置从用户数据根 dataRoot 读，development 模式下它不是 --app-root。
    const wakeup = captureScheduledWakeupContext()
    const client = createRuntimeClient({
      runtimePath,
      appRoot: config.appRoot,
      dataRoot: config.dataRoot,
      env: {
        ...getFluxdownInstallEnvironment(),
        AUTO_MAS_SCHEDULED_WAKEUP: wakeup.scheduledWakeup ? '1' : undefined,
        // resume 先于第二实例事件，是否有待运行定时由后端配置判定。
        AUTO_MAS_SYSTEM_RESUME: wakeup.resumedAt,
      },
    })

    if (config.mode === 'development') {
      const failure = await this.ensureDevelopmentRuntimeEnvironment(client, config)
      if (failure) return failure
    } else {
      const stdoutLines: string[] = []
      const stderrLines: string[] = []
      const otherLines: string[] = []
      const captureLog = (event: RuntimeLogEvent) => {
        const lines =
          event.stream === 'stdout'
            ? stdoutLines
            : event.stream === 'stderr'
              ? stderrLines
              : otherLines
        pushBoundedLine(lines, event.message, RUNTIME_STARTUP_LOG_LINE_LIMIT)
      }
      try {
        const current = await this.runRuntimePreparation(client, ['workspace', 'check'], captureLog)
        if (!current.success)
          return this.buildRuntimeStartFailure(current, stdoutLines, stderrLines, otherLines)
        stdoutLines.length = 0
        stderrLines.length = 0
        otherLines.length = 0
        const details = current.result.details
        const currentVersion =
          details.healthy === true && typeof details.version === 'string'
            ? details.version
            : undefined
        const version = resolveRuntimeTargetVersion(currentVersion)
        const prepared = await this.runRuntimePreparation(
          client,
          ['bootstrap', '--version', version, '--if-needed'],
          captureLog
        )
        if (!prepared.success)
          return this.buildRuntimeStartFailure(prepared, stdoutLines, stderrLines, otherLines)
        this.runtimeUpdateReady = null
        // 日常启动不检查、不更新 Runtime：版本对齐只发生在完整初始化链路（第 0 步）里，
        // 这条路只把现有 exe 拿来监督后端。exe 被杀软还原、上次替换半途而废等情形由定位
        // exe 的 `resolveRuntimeExecutable()` / `recoverRuntimeBackup()` 在本函数开头处理。
      } catch (error) {
        return this.buildRuntimeStartFailure(error, stdoutLines, stderrLines, otherLines)
      }
    }
    if (this.runtimeStopping) {
      return { success: false, error: '正在关闭后端，取消启动' }
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
    const superviseStartedAt = performance.now()
    try {
      // 握手前尚无 supervise 句柄，退出仍须回收到这个客户端持有的进程。
      this.runtimeClients.add(client)
      handle = await client.supervise({
        mode: config.mode,
        repo: config.repo,
        // 端口按应用环境隔离，不随 Runtime 托管模式改变；端点仍采纳 running 事件。
        port,
        shutdownTimeoutSeconds: BACKEND_SHUTDOWN_SECONDS,
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
          logger.info(
            `[启动计时] 桌面/Runtime 报告后端就绪，阶段 ${(performance.now() - superviseStartedAt).toFixed(1)} ms`
          )
          scheduledWakeupBackendReady()
          resolveReady(baseUrl)
        },
      })
      logger.info(
        `[启动计时] 桌面/Runtime 监督握手，阶段 ${(performance.now() - superviseStartedAt).toFixed(1)} ms`
      )
    } catch (error) {
      // 握手阶段的失败（可执行文件缺失、spawn 被拒、协议不匹配、参数错误）都在这里收敛。
      return this.buildRuntimeStartFailure(error, stdoutLines, stderrLines)
    } finally {
      if (!client.hasActiveSessions) this.runtimeClients.delete(client)
    }

    // supervise 独立于一次性准备命令：即使仍在等待就绪，也只能通过 shutdown 请求收尾。
    const releaseStartup = () => {
      if (this.startingRuntimeHandle === handle) this.startingRuntimeHandle = null
    }
    this.startingRuntimeHandle = handle
    void handle.closed.then(releaseStartup)
    if (this.runtimeStopping) await this.stopBackendViaRuntime(handle)

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
      // 采纳句柄前必须确认这次跑起来的后端就是期望版本（issue #30）；
      // 不匹配时先关闭 Runtime 再报错，绝不静默接管旧版本后端。
      try {
        this.assertBackendVersionMatches(
          await this.fetchRunningBackendVersion(outcome.baseUrl, 5000)
        )
      } catch (error) {
        const message = error instanceof Error ? error.message : String(error)
        logger.error(`后端版本校验失败，关闭 Runtime: ${message}`)
        try {
          await handle.shutdown({ timeoutMs: RUNTIME_SHUTDOWN_TIMEOUT_MS })
        } catch (shutdownError) {
          const shutdownMessage =
            shutdownError instanceof Error ? shutdownError.message : String(shutdownError)
          logger.warn(`关闭版本不匹配的 Runtime 未确认完成: ${shutdownMessage}`)
        }
        return this.buildRuntimeStartFailure(error, stdoutLines, stderrLines)
      }
      if (this.runtimeStopping) {
        const stopped = await ended
        return this.buildRuntimeStartFailure(
          'result' in stopped ? stopped.result : stopped.error,
          stdoutLines,
          stderrLines
        )
      }
      releaseStartup()
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
    config: RuntimeLaunchConfig
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
      outcome = await this.runRuntimePreparation(client, ['environment', 'ensure'], event => {
        const lines = event.stream === 'stderr' ? stderrLines : stdoutLines
        pushBoundedLine(lines, event.message, RUNTIME_STARTUP_LOG_LINE_LIMIT)
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
    void handle.closed.then(onFinished)
  }

  private clearRuntimeState(handle: RuntimeSuperviseHandle): void {
    if (this.runtimeHandle !== handle) return
    this.runtimeHandle = null
    this.runtimeBaseUrl = null
    this.startTime = null
    this.notifyStatusChange()
  }

  /**
   * 把 Runtime 的失败终态或调用侧异常转成启动失败结果。
   *
   * `logs` 保持 `[stdout]…\n\n[stderr]…` 的整块格式，现有失败界面不需要改动；`code` /
   * `retryable` / `remediation` 供界面判断可用操作，界面不解析日志或中文文案。
   */
  private buildRuntimeStartFailure(
    reason: RuntimeRunResult | unknown,
    stdoutLines: string[],
    stderrLines: string[],
    otherLines: string[] = []
  ): BackendStartResult {
    if (isRuntimeClientError(reason)) {
      const logs = this.formatRuntimeStartupLogs(
        stdoutLines,
        stderrLines,
        reason.details.stderr,
        otherLines
      )
      logger.error(`Runtime 调用失败: ${reason.code} ${reason.message}`)
      // details 里带着每次尝试的来源与失败种类（git 克隆会先试 cnb 再试 github）。
      // 只打 code + message 的话，日志里看不出是哪个源为什么挂——例如 cnb 秒答但缺
      // 目标分支、github 连接超时，最终只显示后者，真根因被盖住。stderr 已并进 logs，
      // 这里排掉避免重复整块输出。
      const diagnostics = Object.fromEntries(
        Object.entries(reason.details).filter(([key]) => key !== 'stderr')
      )
      if (Object.keys(diagnostics).length > 0) {
        let rendered: string
        try {
          rendered = JSON.stringify(diagnostics)
        } catch {
          rendered = String(diagnostics)
        }
        logger.error(`Runtime 失败详情: ${rendered}`)
      }
      return {
        success: false,
        error: reason.message,
        logs,
        code: reason.code,
        retryable: reason.retryable,
        remediation: [...reason.remediation],
        runtimeFailure: {
          command: reason.details.command,
          processExited: reason.details.processExited,
        },
      }
    }

    if (this.isRuntimeRunResult(reason)) {
      const logs = this.formatRuntimeStartupLogs(
        stdoutLines,
        stderrLines,
        reason.stderr,
        otherLines
      )
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
      logs: this.formatRuntimeStartupLogs(stdoutLines, stderrLines, undefined, otherLines),
    }
  }

  private isRuntimeRunResult(value: unknown): value is RuntimeRunResult {
    return typeof value === 'object' && value !== null && 'result' in value && 'code' in value
  }

  /** Runtime 自身的 stderr 诊断并入 `[stderr]` 块，避免后端没起来时失败界面一片空白。 */
  private formatRuntimeStartupLogs(
    stdoutLines: string[],
    stderrLines: string[],
    runtimeStderr?: string,
    otherLines: string[] = []
  ): string | undefined {
    const boundedStdout: string[] = []
    const boundedStderr: string[] = []
    for (const line of stdoutLines)
      pushBoundedLine(boundedStdout, line, RUNTIME_STARTUP_LOG_LINE_LIMIT)
    for (const line of stderrLines)
      pushBoundedLine(boundedStderr, line, RUNTIME_STARTUP_LOG_LINE_LIMIT)
    const diagnostics = runtimeStderr?.slice(-RUNTIME_STARTUP_LOG_CHAR_LIMIT).trimEnd()
    if (diagnostics) {
      for (const line of diagnostics.split(/\r?\n/)) {
        pushBoundedLine(boundedStderr, line, RUNTIME_STARTUP_LOG_LINE_LIMIT)
      }
    }
    const formatted = formatStartupLogs(boundedStdout, boundedStderr)
    const other = otherLines.join('\n').trimEnd()
    return (
      [formatted, other ? `[other]\n${other}` : undefined].filter(Boolean).join('\n\n') || undefined
    )
  }

  /**
   * 经 Runtime 停止后端：只向 stdin 发 shutdown，不再 taskkill python。
   *
   * 关闭超时由 `handle.shutdown` 兜底 kill Runtime 进程本身，后端进程树由 Runtime 的
   * Job Object 收走，这里不触碰 processManager 的全局清理。
   */
  private async stopBackendViaRuntime(
    handle: RuntimeSuperviseHandle | null = this.runtimeHandle
  ): Promise<BackendStopResult> {
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
      if (this.hasRuntimeProcessExited(error)) {
        this.clearRuntimeState(handle)
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

  /** Runtime 就绪后下发的后端地址；尚未就绪时返回 null。 */
  getRuntimeApiEndpoints(): BackendApiEndpoints | null {
    if (!this.runtimeBaseUrl) return null
    return {
      local: this.runtimeBaseUrl,
      websocket: deriveWebsocketEndpoint(this.runtimeBaseUrl),
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

  /**
   * 停止后端服务
   * 通过 Runtime shutdown 关闭后端
   */
  stopBackend(): Promise<BackendStopResult> {
    this.stopRequested = true
    if (this.stopFlight) return this.stopFlight
    const cancelled = this.cancelRuntimePreparations()
    // 停止请求先打断启动等待，再进入队列收口；不能排在尚未就绪的 start 后才发 shutdown。
    const startingStopped = this.stopBackendViaRuntime(this.startingRuntimeHandle)
    const operation = this.enqueueOperation(async () => {
      await cancelled
      const result = await startingStopped
      if (!result.success) return result
      return this.stopBackendInternal()
    })
    this.stopFlight = operation
    void operation.then(
      () => {
        if (this.stopFlight === operation) {
          this.stopFlight = null
          this.stopRequested = false
        }
      },
      () => {
        if (this.stopFlight === operation) {
          this.stopFlight = null
          this.stopRequested = false
        }
      }
    )
    return operation
  }
  private async stopBackendInternal(): Promise<BackendStopResult> {
    await this.cancelRuntimePreparations()
    if (this.startingRuntimeHandle) {
      const result = await this.stopBackendViaRuntime(this.startingRuntimeHandle)
      if (!result.success) return result
    }
    return this.stopBackendViaRuntime()
  }

  /**
   * 重启后端服务
   */
  restartBackend(
    options?: BackendStartOptions,
    reason: 'manual' | 'recovery' = 'manual'
  ): Promise<BackendStartResult> {
    if (this.restartFlight) return this.restartFlight
    const telemetry = beginMainFeature('backend_restart_finished')
    const operation = this.enqueueOperation(async () => {
      if (this.stopRequested) {
        return { success: false, error: '强制停止已请求，取消后端重启' }
      }
      logger.info('重启后端服务')
      const stopResult = await this.stopBackendInternal()
      if (!stopResult.success) return stopResult
      if (this.stopRequested) {
        return { success: false, error: '强制停止已请求，取消后端重启' }
      }
      return this.startBackendInternal(options)
    })
    this.restartFlight = operation
    void operation.then(
      result =>
        telemetry.finish({ reason_kind: reason, outcome: result.success ? 'success' : 'failure' }),
      () => telemetry.finish({ reason_kind: reason, outcome: 'unknown' })
    )
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

  /** 从健康检查响应里提取后端版本；未上报或格式异常时返回 null。 */
  private extractHealthVersion(payload: unknown): string | null {
    if (!payload || typeof payload !== 'object') return null
    const version = (payload as { version?: unknown }).version
    return typeof version === 'string' && version.trim() !== '' ? version : null
  }

  /**
   * 读取目标地址上正在运行的后端版本。
   * 返回 null 表示「无法确认版本」（不可达、响应异常或协议过旧未上报），由调用方 fail-closed。
   */
  private async fetchRunningBackendVersion(
    apiEndpoint: string,
    timeoutMs: number
  ): Promise<string | null> {
    try {
      const healthUrl = `${apiEndpoint}${this.startupHealthPath}`
      const response = await this.fetchWithTimeout(healthUrl, { method: 'GET' }, timeoutMs)
      if (!response.ok) return null
      return this.extractHealthVersion(await response.json())
    } catch {
      return null
    }
  }

  /**
   * 前后端版本一致性闸门（issue #30）：启动服务必须保证前后端版本匹配，
   * 不匹配或无法确认版本都要显式报错，绝不静默复用旧版本后端。
   */
  private assertBackendVersionMatches(actual: string | null): void {
    const expected = resolveRuntimeTargetVersion()
    if (actual !== null && toRuntimeVersion(actual) === expected) return
    const actualText = actual ?? '未上报（后端不可达或健康检查协议过旧）'
    throw new Error(
      `后端版本不匹配：期望 ${expected}，实际 ${actualText}；请更新后端或关闭旧后端后重试`
    )
  }
  getStatus(): BackendStatus {
    return {
      isRunning: this.runtimeHandle !== null,
      pid: this.runtimeHandle?.pid,
      startTime: this.startTime || undefined,
      runtimeSupervised: true,
    }
  }

  /** 检查 managed 受管仓库的同分支远端 Commit，并在后台准备可供下次启动启用的更新。 */
  checkRuntimeBackendUpdate(): Promise<RuntimeBackendUpdateCheck> {
    if (this.runtimeStopping || this.startFlight) return Promise.resolve({ updateAvailable: false })
    if (this.runtimeUpdateReady) return Promise.resolve(this.runtimeUpdateReady)
    if (this.runtimeUpdateFlight) return this.runtimeUpdateFlight
    const operation = this.prepareRuntimeBackendUpdate()
      .then(result => {
        if (result.staged) this.runtimeUpdateReady = result
        if (result.error) logger.debug(`后台后端更新未完成: ${result.error}`)
        return result
      })
      .finally(() => {
        this.runtimeUpdateFlight = null
      })
    this.runtimeUpdateFlight = operation
    return operation
  }

  private async prepareRuntimeBackendUpdate(): Promise<RuntimeBackendUpdateCheck> {
    const config = resolveRuntimeLaunchConfig(this.appRoot)
    if (config.mode !== 'managed' || !config.runtimePath) return { updateAvailable: false }
    try {
      const client = createRuntimeClient({
        runtimePath: config.runtimePath,
        appRoot: config.appRoot,
        dataRoot: config.dataRoot,
      })
      const outcome = await this.runRuntimePreparation(client, ['workspace', 'check', '--remote'])
      if (!outcome.success) {
        return { updateAvailable: false, error: `${outcome.code}: ${outcome.result.message}` }
      }
      const details = outcome.result.details
      const updateAvailable = details.updateAvailable === true
      if (updateAvailable) {
        const version = typeof details.version === 'string' ? details.version : undefined
        if (!version) {
          return {
            updateAvailable: true,
            staged: false,
            currentCommit: typeof details.commit === 'string' ? details.commit : undefined,
            remoteCommit:
              typeof details.remoteCommit === 'string' ? details.remoteCommit : undefined,
            error: 'Runtime 远端检查未返回当前版本',
          }
        }
        const stageOutcome = await this.runRuntimePreparation(client, [
          'workspace',
          'stage',
          '--version',
          version,
        ])
        if (!stageOutcome.success) {
          return {
            updateAvailable: true,
            staged: false,
            currentCommit: typeof details.commit === 'string' ? details.commit : undefined,
            remoteCommit:
              typeof details.remoteCommit === 'string' ? details.remoteCommit : undefined,
            error: `${stageOutcome.code}: ${stageOutcome.result.message}`,
          }
        }
        return {
          updateAvailable,
          staged: stageOutcome.result.details.staged === true,
          currentCommit: typeof details.commit === 'string' ? details.commit : undefined,
          remoteCommit:
            typeof stageOutcome.result.details.commit === 'string'
              ? stageOutcome.result.details.commit
              : undefined,
          commitMessage:
            typeof stageOutcome.result.details.commitMessage === 'string'
              ? stageOutcome.result.details.commitMessage
              : undefined,
        }
      }
      return {
        updateAvailable,
        staged: false,
        currentCommit: typeof details.commit === 'string' ? details.commit : undefined,
        remoteCommit: typeof details.remoteCommit === 'string' ? details.remoteCommit : undefined,
      }
    } catch (error) {
      return {
        updateAvailable: false,
        error: error instanceof Error ? error.message : String(error),
      }
    }
  }

  /** 跟踪一次性准备命令，使退出时的取消覆盖握手和下载两个阶段。 */
  private async runRuntimePreparation(
    client: RuntimeClient,
    args: string[],
    onLog?: (event: RuntimeLogEvent) => void
  ): Promise<RuntimeRunResult> {
    if (this.runtimeStopping) throw new Error('应用正在关闭，取消后端准备')
    this.runtimeClients.add(client)
    try {
      return await client.run(args, {
        onLog,
        onProgress: event => logger.debug(`Runtime ${event.stage}: ${event.message}`),
      })
    } finally {
      if (!client.hasActiveSessions) this.runtimeClients.delete(client)
    }
  }

  private async cancelRuntimePreparations(): Promise<void> {
    this.runtimeStopping = true
    await Promise.all([...this.runtimeClients].map(client => client.stop()))
    this.runtimeClients.clear()
  }

  /**
   * 设置状态回调
   */
  setStatusCallback(callback: BackendStatusCallback): void {
    this.statusCallback = callback
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
