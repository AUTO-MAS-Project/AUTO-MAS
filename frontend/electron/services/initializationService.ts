/**
 * 初始化总流程服务
 * 重构版本 - 协调所有初始化步骤
 */

import { MirrorService } from './mirrorService'
import { PythonInstaller, PipInstaller, GitInstaller } from './environmentService'
import { RepositoryService } from './repositoryService'
import { DependencyService } from './dependencyService'
import { BackendService } from './backendService'
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
  /** Runtime 链路给出的机器可读段状态；旧链路不产生，界面按缺省处理。 */
  status?: InitializationStageStatus
  /** 本次进度来自哪条链路；旧链路不产生，界面按 `off` 处理。 */
  runtimeMode?: RuntimeLaunchMode
  details?: {
    checkInfo?: unknown // 可以是 EnvironmentCheckResult, RepositoryCheckResult, 或 DependencyCheckResult
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
  /** 以下五项只有 Runtime 链路产生，旧链路保持 undefined；界面（W9d）按需消费。 */
  code?: string
  retryable?: boolean
  remediation?: RuntimeRemediation[]
  logs?: string
  logPath?: string
}

// ==================== 初始化服务类 ====================

export class InitializationService {
  private appRoot: string
  private mirrorService: MirrorService
  private backendService: BackendService
  private targetBranch: string
  /** Runtime 链路的编排器；灰度开关关闭时始终为 null。 */
  private runtimeService: RuntimeInitializationService | null = null

  constructor(appRoot: string, targetBranch: string = 'dev') {
    this.appRoot = appRoot
    this.mirrorService = new MirrorService(appRoot)
    this.backendService = new BackendService(appRoot, this.mirrorService)
    this.targetBranch = targetBranch
  }

  /**
   * 取本次生命周期的 Runtime 编排器；灰度开关关闭时返回 null。
   *
   * 单步重试与 doctor 走的是另外的 IPC 入口，需要复用同一个实例才能记住上一次失败
   * 给出的处置动作（决定重试用 `dependencies sync` 还是 `dependencies rebuild`）。
   */
  getRuntimeService(): RuntimeInitializationService | null {
    const launchConfig = resolveRuntimeLaunchConfig(this.appRoot)
    if (launchConfig.mode === 'off') {
      this.runtimeService = null
      return null
    }

    if (!this.runtimeService || this.runtimeService.launchConfig.mode !== launchConfig.mode) {
      this.runtimeService = new RuntimeInitializationService({ launchConfig })
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
    const completedStages: string[] = []
    const totalStages = startBackend ? 7 : 6

    // 灰度开关打开后整条初始化都走 Runtime，绝不与旧链路混用：两条链路的目录布局、
    // Python 来源与依赖管理器都不同，中途混用只会装出一个谁都不认的环境。
    const launchConfig = resolveRuntimeLaunchConfig(this.appRoot)
    if (launchConfig.mode === 'development') {
      return this.initializeViaDevelopmentRuntime(onProgress, startBackend)
    }
    if (launchConfig.mode === 'managed') {
      return this.initializeViaRuntime(onProgress, startBackend)
    }

    try {
      // 阶段 1: 初始化镜像源配置
      onProgress?.({
        stage: 'mirror',
        stageIndex: 1,
        totalStages,
        progress: 0,
        message: '正在初始化镜像源配置...',
      })

      await this.mirrorService.initialize()
      completedStages.push('mirror')

      onProgress?.({
        stage: 'mirror',
        stageIndex: 1,
        totalStages,
        progress: 100,
        message: '镜像源配置初始化完成',
      })

      // 阶段 2: 安装 Python
      onProgress?.({
        stage: 'python',
        stageIndex: 2,
        totalStages,
        progress: 0,
        message: '正在安装 Python...',
      })

      const pythonInstaller = new PythonInstaller(this.appRoot, this.mirrorService)
      const pythonResult = await pythonInstaller.install(installProgress => {
        onProgress?.({
          stage: 'python',
          stageIndex: 2,
          totalStages,
          progress: installProgress.progress,
          message: installProgress.message,
          details: installProgress.details,
        })
      })

      if (!pythonResult.success) {
        return {
          success: false,
          error: pythonResult.error,
          completedStages,
          failedStage: 'python',
        }
      }

      completedStages.push('python')

      // 阶段 3: 安装 Pip
      onProgress?.({
        stage: 'pip',
        stageIndex: 3,
        totalStages,
        progress: 0,
        message: '正在安装 Pip...',
      })

      const pipInstaller = new PipInstaller(this.appRoot, this.mirrorService)
      const pipResult = await pipInstaller.install(installProgress => {
        onProgress?.({
          stage: 'pip',
          stageIndex: 3,
          totalStages,
          progress: installProgress.progress,
          message: installProgress.message,
          details: installProgress.details,
        })
      })

      if (!pipResult.success) {
        return {
          success: false,
          error: pipResult.error,
          completedStages,
          failedStage: 'pip',
        }
      }

      completedStages.push('pip')

      // 阶段 4: 安装 Git
      onProgress?.({
        stage: 'git',
        stageIndex: 4,
        totalStages,
        progress: 0,
        message: '正在安装 Git...',
      })

      const gitInstaller = new GitInstaller(this.appRoot, this.mirrorService)
      const gitResult = await gitInstaller.install(installProgress => {
        onProgress?.({
          stage: 'git',
          stageIndex: 4,
          totalStages,
          progress: installProgress.progress,
          message: installProgress.message,
          details: installProgress.details,
        })
      })

      if (!gitResult.success) {
        return {
          success: false,
          error: gitResult.error,
          completedStages,
          failedStage: 'git',
        }
      }

      completedStages.push('git')

      // 阶段 5: 拉取源码
      onProgress?.({
        stage: 'repository',
        stageIndex: 5,
        totalStages,
        progress: 0,
        message: '正在拉取源码...',
      })

      const repositoryService = new RepositoryService(
        this.appRoot,
        this.mirrorService,
        this.targetBranch
      )
      const repoResult = await repositoryService.pullRepository(repoProgress => {
        onProgress?.({
          stage: 'repository',
          stageIndex: 5,
          totalStages,
          progress: repoProgress.progress,
          message: repoProgress.message,
          details: repoProgress.details,
        })
      })

      if (!repoResult.success) {
        return {
          success: false,
          error: repoResult.error,
          completedStages,
          failedStage: 'repository',
        }
      }

      completedStages.push('repository')

      // 阶段 6: 安装依赖
      onProgress?.({
        stage: 'dependency',
        stageIndex: 6,
        totalStages,
        progress: 0,
        message: '正在安装依赖...',
      })

      const dependencyService = new DependencyService(this.appRoot, this.mirrorService)
      const depResult = await dependencyService.installDependencies(depProgress => {
        onProgress?.({
          stage: 'dependency',
          stageIndex: 6,
          totalStages,
          progress: depProgress.progress,
          message: depProgress.message,
          details: depProgress.details,
        })
      })

      if (!depResult.success) {
        return {
          success: false,
          error: depResult.error,
          completedStages,
          failedStage: 'dependency',
        }
      }

      completedStages.push('dependency')

      // 阶段 7: 启动后端（可选）
      if (startBackend) {
        onProgress?.({
          stage: 'backend',
          stageIndex: 7,
          totalStages,
          progress: 0,
          message: '正在启动后端服务...',
        })

        const backendResult = await this.backendService.startBackend()

        if (!backendResult.success) {
          return {
            success: false,
            error: backendResult.error,
            completedStages,
            failedStage: 'backend',
          }
        }

        const status = this.backendService.getStatus()
        onProgress?.({
          stage: 'backend',
          stageIndex: 7,
          totalStages,
          progress: 100,
          message: `后端服务已启动，PID: ${status.pid}`,
        })

        completedStages.push('backend')
      }

      // 完成
      onProgress?.({
        stage: 'complete',
        stageIndex: totalStages,
        totalStages,
        progress: 100,
        message: '初始化完成',
      })

      return {
        success: true,
        completedStages,
      }
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.error(`初始化失败: ${errorMsg}`)

      return {
        success: false,
        error: errorMsg,
        completedStages,
      }
    }
  }

  // ==================== Runtime 初始化链路 ====================

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
      })
  }

  /**
   * development 模式：跳过全部安装步骤，直接起后端。
   *
   * 开发检出自带 `.venv`，Runtime 的 development 模式只监督这份源码，既不创建也不更新它。
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
   * managed 模式：一次 `bootstrap --version <应用自身版本>` 顶掉原来的五步链。
   *
   * 目标版本用应用自身版本（Runtime 据此拼 `release/<版本>` 分支名）；更新流程的目标版本
   * 由更新任务另行给出，不走这里。
   */
  private async initializeViaRuntime(
    onProgress?: InitializationProgressCallback,
    startBackend: boolean = true
  ): Promise<InitializationResult> {
    const runtimeService = this.getRuntimeService()
    if (!runtimeService) {
      // getRuntimeService 只在 off 模式返回 null，这里进不来；留一个显式失败而不是断言。
      return { success: false, error: 'Runtime 链路未启用', completedStages: [] }
    }

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
   * 复用；灰度开关关闭时返回 null，调用方继续走旧链路。
   */
  async retryStageViaRuntime(
    stage: InitializationRunStage,
    onProgress?: InitializationProgressCallback,
    mirrorKey?: string,
    mode: RuntimeRetryMode = 'auto'
  ): Promise<RuntimeStageOutcome | null> {
    const runtimeService = this.getRuntimeService()
    if (!runtimeService) return null

    return runtimeService.retryStage(
      stage,
      this.forwardRuntimeProgress(onProgress, 7),
      mirrorKey,
      mode
    )
  }

  /**
   * 仅更新源码和依赖（用于已初始化的环境）
   */
  async updateOnly(onProgress?: InitializationProgressCallback): Promise<InitializationResult> {
    const completedStages: string[] = []
    const totalStages = 2

    try {
      // 初始化镜像源配置
      await this.mirrorService.initialize()

      // 阶段 1: 拉取源码
      onProgress?.({
        stage: 'repository',
        stageIndex: 1,
        totalStages,
        progress: 0,
        message: '正在更新源码...',
      })

      const repositoryService = new RepositoryService(
        this.appRoot,
        this.mirrorService,
        this.targetBranch
      )
      const repoResult = await repositoryService.pullRepository(repoProgress => {
        onProgress?.({
          stage: 'repository',
          stageIndex: 1,
          totalStages,
          progress: repoProgress.progress,
          message: repoProgress.message,
          details: repoProgress.details,
        })
      })

      if (!repoResult.success) {
        return {
          success: false,
          error: repoResult.error,
          completedStages,
          failedStage: 'repository',
        }
      }

      completedStages.push('repository')

      // 阶段 2: 安装依赖
      onProgress?.({
        stage: 'dependency',
        stageIndex: 2,
        totalStages,
        progress: 0,
        message: '正在更新依赖...',
      })

      const dependencyService = new DependencyService(this.appRoot, this.mirrorService)
      const depResult = await dependencyService.installDependencies(depProgress => {
        onProgress?.({
          stage: 'dependency',
          stageIndex: 2,
          totalStages,
          progress: depProgress.progress,
          message: depProgress.message,
          details: depProgress.details,
        })
      })

      if (!depResult.success) {
        return {
          success: false,
          error: depResult.error,
          completedStages,
          failedStage: 'dependency',
        }
      }

      completedStages.push('dependency')

      // 完成
      onProgress?.({
        stage: 'complete',
        stageIndex: totalStages,
        totalStages,
        progress: 100,
        message: '更新完成',
      })

      return {
        success: true,
        completedStages,
      }
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.error(`更新失败: ${errorMsg}`)

      return {
        success: false,
        error: errorMsg,
        completedStages,
      }
    }
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
    return this.backendService
  }
}
