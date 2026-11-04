/**
 * 初始化总流程服务
 * 协调 Runtime 准备与后端启动
 */

import { MirrorService } from './mirrorService'
import { BackendService } from './backendService'
import { getBackendOwnership } from './instanceConfig'
import { RUNTIME_KILL_WAIT_MS, RUNTIME_STOP_TIMEOUT_MS, waitForSettle } from './runtime/shutdown'
import { RuntimeLaunchMode, RuntimeRemediation, resolveRuntimeLaunchConfig } from './runtime'
import {
  BootstrapProgressUpdate,
  INITIALIZATION_STAGE_INDEX,
  InitializationRunStage,
  InitializationStage,
  InitializationStageStatus,
  RuntimeInitializationService,
  RuntimeRetryMode,
  RuntimeStageOutcome,
  emitDevelopmentSkipProgress,
} from './runtimeInitializationService'

// 导入日志服务
import { getLogger } from './logger'
const logger = getLogger('初始化服务')

// ==================== 类型定义 ====================

export interface InitializationProgress {
  stage: InitializationStage
  stageIndex: number
  totalStages: number
  progress: number
  message: string
  /** Runtime 给出的机器可读段状态。 */
  status?: InitializationStageStatus
  /** 本次进度对应的 Runtime 模式。 */
  runtimeMode?: RuntimeLaunchMode
  /** 当前阶段没有可靠总量，界面应展示持续活动状态而不是精确百分比。 */
  indeterminate?: boolean
  /** 以下七项只有 Runtime 链路产生，原样透传 `BootstrapProgressUpdate` 的同名字段。 */
  runtimeStage?: string
  runtimeStatus?: string
  item?: string
  source?: string
  bytesPerSecond?: number
  current?: number
  total?: number
  details?: {
    checkInfo?: unknown // Runtime 检查详情
    currentMirror?: string
    mirrorProgress?: { current: number; total: number }
    downloadSpeed?: number
    downloadSize?: number
    operationDesc?: string
  }
}

export type InitializationProgressCallback = (progress: InitializationProgress) => void

export interface InitializationResult {
  success: boolean
  error?: string
  completedStages: string[]
  failedStage?: string
  failureOrigin?: 'runtime_binary'
  /** 失败时按需透传 Runtime 的结构化详情。 */
  code?: string
  retryable?: boolean
  remediation?: RuntimeRemediation[]
  logs?: string
  logPath?: string
}

// ==================== 初始化服务类 ====================

export class InitializationService {
  readonly ownsBackend = getBackendOwnership() === 'owned'
  private appRoot: string
  private mirrorService: MirrorService
  private backendService: BackendService
  /** 同一初始化生命周期复用编排器，保留失败后的处置动作。 */
  private runtimeService: RuntimeInitializationService | null = null

  constructor(appRoot: string) {
    this.appRoot = appRoot
    this.mirrorService = new MirrorService(appRoot)
    this.backendService = new BackendService(appRoot)
  }

  private desktopStartup: Promise<InitializationResult> | null = null
  private desktopState: {
    runtimeMode: RuntimeLaunchMode
    flowKind: 'startup' | 'first-run' | 'update'
    fullInitialization: boolean
    state: 'running' | 'ready' | 'failed'
    progress: InitializationProgress[]
  } | null = null
  private closing = false
  private environmentOperation: Promise<unknown> | null = null
  private stopFlight: Promise<void> | null = null
  private shutdownRequested = false

  /** 进程拥有启动任务；晚到的窗口读取快照并接回同一结果，包括失败。 */
  startDesktopStartup(
    preferences: { version: string; initializedVersion?: string; autoUpdate: boolean },
    onProgress?: InitializationProgressCallback
  ): Promise<InitializationResult> {
    if (!this.ownsBackend) return Promise.resolve({ success: true, completedStages: [] })
    if (this.desktopStartup) return this.desktopStartup
    const runtimeMode = resolveRuntimeLaunchConfig(this.appRoot).mode
    const fullInitialization =
      runtimeMode === 'managed' &&
      (preferences.autoUpdate || preferences.initializedVersion !== preferences.version)
    this.desktopState = {
      runtimeMode,
      flowKind: fullInitialization
        ? preferences.initializedVersion
          ? 'update'
          : 'first-run'
        : 'startup',
      fullInitialization,
      state: 'running',
      progress: [],
    }
    const state = this.desktopState
    const publish = (progress: InitializationProgress) => {
      const index = state.progress.findIndex(item => item.stage === progress.stage)
      if (index < 0) state.progress.push(progress)
      else state.progress[index] = progress
      onProgress?.(progress)
    }
    // 先登记 Promise，再执行，窗口创建无需等待这条链。
    this.desktopStartup = Promise.resolve()
      .then(async () => {
        if (this.closing) return this.cancelledStartup()
        if (fullInitialization) {
          await this.mirrorService.initialize()
          if (this.closing) return this.cancelledStartup()
          return this.initialize(publish)
        }
        return this.startBackendStage(publish, 7, [])
      })
      .catch((error: unknown): InitializationResult => ({
        success: false,
        completedStages: [],
        failedStage: fullInitialization ? 'python' : 'backend',
        error: error instanceof Error ? error.message : String(error),
      }))
      .then(result => {
        state.state = result.success ? 'ready' : 'failed'
        return result
      })
    return this.desktopStartup
  }

  getDesktopStartupSnapshot() {
    return this.desktopState ? structuredClone(this.desktopState) : null
  }

  waitForDesktopStartup(): Promise<InitializationResult> | null {
    return this.desktopStartup
  }

  /** 显式重试或修复才清除终态；启动期间不允许另一条环境变更链插入。 */
  resetDesktopStartup(): void {
    if (this.desktopState?.state === 'running') throw new Error('启动尚未结束，请稍后再试')
    if (this.closing) throw new Error('应用正在关闭')
    if (this.environmentOperation) throw new Error('运行环境操作尚未结束，请稍后再试。')
    this.desktopStartup = null
    this.desktopState = null
  }

  get isEnvironmentBusy(): boolean {
    return this.environmentOperation !== null || this.runtimeService?.isBusy === true
  }

  /** 手动准备、修复和更新共用占用边界，内部仍复用各服务的启停队列。 */
  async runEnvironmentOperation<T>(operation: () => Promise<T>): Promise<T> {
    this.assertBackendOwnership()
    this.resetDesktopStartup()
    const running = Promise.resolve().then(operation)
    this.environmentOperation = running
    try {
      return await running
    } finally {
      if (this.environmentOperation === running) this.environmentOperation = null
    }
  }

  private cancelledStartup(): InitializationResult {
    return { success: false, completedStages: [], code: 'OPERATION_CANCELLED', error: '启动已取消' }
  }

  /** 取消覆盖镜像准备、Runtime 对齐、bootstrap 和尚未就绪的 supervise。 */
  stopDesktopStartup(shutdown = false): Promise<void> {
    if (!this.ownsBackend) return Promise.resolve()
    this.shutdownRequested ||= shutdown
    if (this.stopFlight) return this.stopFlight
    this.closing = true
    const deadline = Date.now() + RUNTIME_STOP_TIMEOUT_MS + RUNTIME_KILL_WAIT_MS
    this.stopFlight = (async () => {
      const [result] = await Promise.all([
        this.backendService.stopBackend(),
        this.runtimeService?.shutdown(),
      ])
      if (!result.success) throw new Error(result.error || '无法停止后端')
      const settled = await waitForSettle(
        Promise.allSettled([this.desktopStartup, this.environmentOperation]),
        Math.max(0, deadline - Date.now())
      )
      if (!settled) throw new Error('无法确认运行环境操作已结束，请重试退出。')
      this.desktopStartup = null
      this.desktopState = null
      this.runtimeService = null
      this.closing = this.shutdownRequested
    })().finally(() => {
      this.stopFlight = null
    })
    return this.stopFlight
  }

  /**
   * 取本次生命周期的 Runtime 编排器。
   *
   * 单步重试与 doctor 走的是另外的 IPC 入口，需要复用同一个实例才能记住上一次失败
   * 给出的处置动作（决定重试用 `dependencies sync` 还是 `dependencies rebuild`）。
   */
  getRuntimeService(): RuntimeInitializationService {
    this.assertBackendOwnership()
    const launchConfig = resolveRuntimeLaunchConfig(this.appRoot)
    if (!this.runtimeService || this.runtimeService.launchConfig.mode !== launchConfig.mode) {
      this.runtimeService = new RuntimeInitializationService({
        launchConfig,
        mirrorService: this.mirrorService,
      })
    }
    return this.runtimeService
  }

  /**
   * 执行完整的初始化流程
   */
  async initialize(
    onProgress?: InitializationProgressCallback,
    startBackend: boolean = true
  ): Promise<InitializationResult> {
    this.assertBackendOwnership()
    if (resolveRuntimeLaunchConfig(this.appRoot).mode === 'development') {
      return this.initializeViaDevelopmentRuntime(onProgress, startBackend)
    }
    return this.initializeViaRuntime(onProgress, startBackend)
  }

  /** 把 Runtime 的段进度补齐成现有 7 段进度的形状。 */
  private forwardRuntimeProgress(
    onProgress: InitializationProgressCallback | undefined,
    totalStages: number
  ): (update: BootstrapProgressUpdate) => void {
    const runtimeMode = resolveRuntimeLaunchConfig(this.appRoot).mode
    return update =>
      onProgress?.({
        stage: update.stage,
        stageIndex: INITIALIZATION_STAGE_INDEX[update.stage],
        totalStages,
        progress: update.progress,
        message: update.message,
        status: update.status,
        runtimeMode,
        indeterminate: update.indeterminate,
        runtimeStage: update.runtimeStage,
        runtimeStatus: update.runtimeStatus,
        item: update.item,
        source: update.source,
        bytesPerSecond: update.bytesPerSecond,
        current: update.current,
        total: update.total,
      })
  }

  /**
   * development 模式：跳过全部安装步骤，直接起后端。
   *
   * 开发检出自带 `.venv`，Runtime 的 development 模式只监督这份源码，既不创建也不更新它。
   * 唯一要准备的是 Runtime 自己的 uv（`backend supervise` 不下载它），这一步由
   * `backendService` 在 supervise 之前以 `environment ensure` 完成，不占用界面上的段。
   */
  private async initializeViaDevelopmentRuntime(
    onProgress?: InitializationProgressCallback,
    startBackend: boolean = true
  ): Promise<InitializationResult> {
    logger.info('Runtime development 模式：跳过全部安装步骤')
    const totalStages = startBackend ? 7 : 6
    const completedStages = ['mirror', 'python', 'pip', 'git', 'repository', 'dependency']

    emitDevelopmentSkipProgress(this.forwardRuntimeProgress(onProgress, totalStages))

    if (!startBackend) {
      this.emitComplete(onProgress, totalStages)
      return { success: true, completedStages }
    }

    return this.startBackendStage(onProgress, totalStages, completedStages)
  }

  /**
   * managed 模式：一次 `bootstrap --version <应用自身版本>` 完成环境准备。
   *
   * 目标版本用应用自身版本（Runtime 据此拼 `release/<版本>` 分支名）；更新流程的目标版本
   * 由更新任务另行给出，不走这里。
   */
  private async initializeViaRuntime(
    onProgress?: InitializationProgressCallback,
    startBackend: boolean = true
  ): Promise<InitializationResult> {
    const runtimeService = this.getRuntimeService()
    logger.info('Runtime managed 模式：以 bootstrap 完成全部准备工作')
    const totalStages = startBackend ? 7 : 6
    const completedStages: string[] = []

    const outcome = await runtimeService.bootstrap(
      this.forwardRuntimeProgress(onProgress, totalStages)
    )

    if (!outcome.success) {
      return this.buildRuntimeFailure(outcome, completedStages)
    }

    completedStages.push('mirror', 'python', 'pip', 'git', 'repository', 'dependency')

    if (!startBackend) {
      this.emitComplete(onProgress, totalStages)
      return { success: true, completedStages }
    }

    return this.startBackendStage(onProgress, totalStages, completedStages)
  }

  /** Runtime 链路的后端段：仍由 backendService 起 `backend supervise`。 */
  private async startBackendStage(
    onProgress: InitializationProgressCallback | undefined,
    totalStages: number,
    completedStages: string[]
  ): Promise<InitializationResult> {
    if (this.closing) return this.cancelledStartup()
    onProgress?.({
      stage: 'backend',
      stageIndex: INITIALIZATION_STAGE_INDEX.backend,
      totalStages,
      progress: 0,
      message: '正在启动后端服务...',
      status: 'started',
    })

    const backendResult = await this.backendService.startBackend()
    if (!backendResult.success) {
      onProgress?.({
        stage: 'backend',
        stageIndex: INITIALIZATION_STAGE_INDEX.backend,
        totalStages,
        progress: 0,
        message: backendResult.error ?? '后端启动失败',
        status: 'failed',
      })
      return {
        success: false,
        error: backendResult.error,
        completedStages,
        failedStage: 'backend',
        code: backendResult.code,
        retryable: backendResult.retryable,
        remediation: backendResult.remediation,
        logs: backendResult.logs,
      }
    }

    const status = this.backendService.getStatus()
    onProgress?.({
      stage: 'backend',
      stageIndex: INITIALIZATION_STAGE_INDEX.backend,
      totalStages,
      progress: 100,
      message: `后端服务已启动，PID: ${status.pid}`,
      status: 'completed',
    })
    completedStages.push('backend')

    this.emitComplete(onProgress, totalStages)
    return { success: true, completedStages }
  }

  private emitComplete(
    onProgress: InitializationProgressCallback | undefined,
    totalStages: number
  ): void {
    onProgress?.({
      stage: 'complete',
      stageIndex: totalStages,
      totalStages,
      progress: 100,
      message: '初始化完成',
      status: 'completed',
    })
  }

  /** Runtime 失败转成现有失败形状，额外带上结构化字段供 W9d 使用。 */
  private buildRuntimeFailure(
    outcome: RuntimeStageOutcome,
    completedStages: string[]
  ): InitializationResult {
    return {
      success: false,
      error: outcome.error,
      completedStages,
      failedStage: outcome.failedStage,
      failureOrigin: outcome.failureOrigin,
      code: outcome.code,
      retryable: outcome.retryable,
      remediation: outcome.remediation,
      logs: outcome.logs,
      logPath: outcome.logPath,
    }
  }

  /**
   * Runtime 链路下的单步重试。
   *
   * 由各步 IPC handler（`install-python` / `pull-repository` / `install-dependencies` 等）
   * 复用，所有执行均交给 Runtime。
   */
  async retryStageViaRuntime(
    stage: InitializationRunStage,
    onProgress?: InitializationProgressCallback,
    mirrorKey?: string,
    mode: RuntimeRetryMode = 'auto'
  ): Promise<RuntimeStageOutcome> {
    const runtimeService = this.getRuntimeService()

    return runtimeService.retryStage(
      stage,
      this.forwardRuntimeProgress(onProgress, 7),
      mirrorKey,
      mode
    )
  }

  /**
   * 获取镜像源服务实例（用于外部访问）
   */
  getMirrorService(): MirrorService {
    return this.mirrorService
  }

  /**
   * 获取后端服务实例（用于外部访问）
   */
  getBackendService(): BackendService {
    this.assertBackendOwnership()
    return this.backendService
  }

  private assertBackendOwnership(): void {
    if (!this.ownsBackend) throw new Error('当前仅连接外部后端，请在其终端中管理后端。')
  }
}
