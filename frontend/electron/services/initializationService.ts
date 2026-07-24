/**
 * 初始化总流程服务
 * 重构版本 - 协调所有初始化步骤
 */

import { MirrorService } from './mirrorService'
import { PythonInstaller, PipInstaller, GitInstaller } from './environmentService'
import { RepositoryService } from './repositoryService'
import { DependencyService } from './dependencyService'
import { PluginBootstrapService } from './pluginBootstrapService'
import { BackendService } from './backendService'
import { requiresBundledRuntimeLock } from './bundledRuntimePolicy'

// 导入日志服务
import { getLogger } from './logger'
const logger = getLogger('初始化服务')

// ==================== 类型定义 ====================

export interface InitializationProgress {
  stage:
    | 'mirror'
    | 'python'
    | 'uv'
    | 'git'
    | 'repository'
    | 'dependency'
    | 'plugin-bootstrap'
    | 'backend'
    | 'complete'
  stageIndex: number
  totalStages: number
  progress: number
  message: string
  details?: {
    checkInfo?: any // 可以是 EnvironmentCheckResult, RepositoryCheckResult, 或 DependencyCheckResult
    currentMirror?: string
    mirrorProgress?: { current: number; total: number }
    downloadSpeed?: number
    downloadSize?: number
    operationDesc?: string
    currentPackage?: string
    failedPackages?: string[]
    warnings?: Array<{ packageName: string; message: string; kind: string }>
  }
}

export type InitializationProgressCallback = (progress: InitializationProgress) => void

export interface InitializationResult {
  success: boolean
  error?: string
  completedStages: string[]
  failedStage?: string
}

// ==================== 初始化服务类 ====================

export class InitializationService {
  private appRoot: string
  private mirrorService: MirrorService
  private backendService: BackendService
  private targetBranch: string

  constructor(appRoot: string, targetBranch: string = 'dev') {
    this.appRoot = appRoot
    this.mirrorService = new MirrorService(appRoot)
    this.backendService = new BackendService(appRoot, this.mirrorService)
    this.targetBranch = targetBranch
  }

  /** 随包锁定运行时不刷新云端镜像配置，保证离线首启不会等待网络。 */
  private async initializeMirrorConfig(): Promise<void> {
    if (requiresBundledRuntimeLock(this.appRoot)) {
      this.mirrorService.initializeLocal()
      logger.info('随包锁定运行时使用本地/默认镜像配置，跳过 MirrorChyan 云端刷新')
      return
    }

    await this.mirrorService.initialize()
  }

  /**
   * 执行完整的初始化流程
   */
  async initialize(
    onProgress?: InitializationProgressCallback,
    startBackend: boolean = true
  ): Promise<InitializationResult> {
    const completedStages: string[] = []
    const totalStages = startBackend ? 8 : 7

    try {
      // 阶段 1: 初始化镜像源配置
      onProgress?.({
        stage: 'mirror',
        stageIndex: 1,
        totalStages,
        progress: 0,
        message: '正在初始化镜像源配置...',
      })

      await this.initializeMirrorConfig()
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

      // 阶段 3: 安装 uv
      onProgress?.({
        stage: 'uv',
        stageIndex: 3,
        totalStages,
        progress: 0,
        message: '正在安装 uv 包管理器...',
      })

      const pipInstaller = new PipInstaller(this.appRoot, this.mirrorService)
      const pipResult = await pipInstaller.install(installProgress => {
        onProgress?.({
          stage: 'uv',
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

      // 阶段 7: 预装推荐插件包
      onProgress?.({
        stage: 'plugin-bootstrap',
        stageIndex: 7,
        totalStages,
        progress: 0,
        message: '正在预装推荐插件包...',
      })

      const pluginBootstrapService = new PluginBootstrapService(this.appRoot, this.mirrorService)
      const bootstrapResult = await pluginBootstrapService.installPackages(bootstrapProgress => {
        onProgress?.({
          stage: 'plugin-bootstrap',
          stageIndex: 7,
          totalStages,
          progress: bootstrapProgress.progress,
          message: bootstrapProgress.message,
          details: bootstrapProgress.details,
        })
      })

      if (!bootstrapResult.success) {
        return {
          success: false,
          error: bootstrapResult.error,
          completedStages,
          failedStage: 'plugin-bootstrap',
        }
      }

      completedStages.push('plugin-bootstrap')

      // 阶段 8: 启动后端（可选）
      if (startBackend) {
        onProgress?.({
          stage: 'backend',
          stageIndex: 8,
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
          stageIndex: 8,
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

  /**
   * 仅更新源码和依赖（用于已初始化的环境）
   */
  async updateOnly(onProgress?: InitializationProgressCallback): Promise<InitializationResult> {
    const completedStages: string[] = []
    let shouldRestartBackend = false
    let totalStages = 3
    let repositoryStageIndex = 1
    let dependencyStageIndex = 2
    let pluginBootstrapStageIndex = 3
    let backendStageIndex = 3
    let backendStoppedForUpdate = false
    let repositoryCommitted = false

    const failUpdate = async (
      error: string | undefined,
      failedStage?: string
    ): Promise<InitializationResult> => {
      let finalError = error || '更新失败'
      if (backendStoppedForUpdate) {
        if (repositoryCommitted) {
          finalError = `${finalError}; 运行时源码已经变更，后端已保持停止，必须完成修复后再启动`
          logger.error('更新在源码部署后失败，后端保持停止以避免启动混合版本运行时')
        } else {
          logger.warn('源码尚未部署，尝试恢复更新前运行中的后端服务')
          const restoreResult = await this.backendService.startBackend()
          if (restoreResult.success) {
            backendStoppedForUpdate = false
            logger.info('更新失败后已恢复后端服务')
          } else {
            finalError = `${finalError}; 后端恢复失败: ${restoreResult.error || '未知错误'}`
            logger.error(`更新失败后无法恢复后端服务: ${restoreResult.error || '未知错误'}`)
          }
        }
      }

      return {
        success: false,
        error: finalError,
        completedStages,
        failedStage,
      }
    }

    try {
      // 初始化镜像源配置
      await this.initializeMirrorConfig()

      // Windows 上运行中的 Python 进程可能持有源码、插件或 DLL 文件锁。
      // 在任何部署或安装操作之前先安全停止，由本 Electron 实例在结束后恢复。
      const stopResult = await this.backendService.stopBackendForRuntimeMutation()
      if (!stopResult.success) {
        return {
          success: false,
          error: stopResult.error,
          completedStages,
          failedStage: 'backend',
        }
      }

      shouldRestartBackend = stopResult.wasRunning
      totalStages = shouldRestartBackend ? 5 : 3
      repositoryStageIndex = shouldRestartBackend ? 2 : 1
      dependencyStageIndex = shouldRestartBackend ? 3 : 2
      pluginBootstrapStageIndex = shouldRestartBackend ? 4 : 3
      backendStageIndex = shouldRestartBackend ? 5 : 3

      if (shouldRestartBackend) {
        onProgress?.({
          stage: 'backend',
          stageIndex: 1,
          totalStages,
          progress: 100,
          message: '后端服务已安全停止，可以更新运行时文件',
        })
        backendStoppedForUpdate = true
        completedStages.push('backend-stop')
      }

      // 阶段 1: 拉取源码
      onProgress?.({
        stage: 'repository',
        stageIndex: repositoryStageIndex,
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
          stageIndex: repositoryStageIndex,
          totalStages,
          progress: repoProgress.progress,
          message: repoProgress.message,
          details: repoProgress.details,
        })
      })

      if (!repoResult.success) {
        return await failUpdate(repoResult.error, 'repository')
      }

      repositoryCommitted = true
      completedStages.push('repository')

      // 阶段 2: 安装依赖
      onProgress?.({
        stage: 'dependency',
        stageIndex: dependencyStageIndex,
        totalStages,
        progress: 0,
        message: '正在更新依赖...',
      })

      const dependencyService = new DependencyService(this.appRoot, this.mirrorService)
      const depResult = await dependencyService.installDependencies(depProgress => {
        onProgress?.({
          stage: 'dependency',
          stageIndex: dependencyStageIndex,
          totalStages,
          progress: depProgress.progress,
          message: depProgress.message,
          details: depProgress.details,
        })
      })

      if (!depResult.success) {
        return await failUpdate(depResult.error, 'dependency')
      }

      completedStages.push('dependency')

      // 阶段 3: 刷新插件引导包。更新模式强制重新安装，确保本地源码和随包 wheel
      // 在版本号未变化时也能覆盖旧的插件代码。
      onProgress?.({
        stage: 'plugin-bootstrap',
        stageIndex: pluginBootstrapStageIndex,
        totalStages,
        progress: 0,
        message: '正在更新插件包...',
      })

      const pluginBootstrapService = new PluginBootstrapService(this.appRoot, this.mirrorService)
      const bootstrapResult = await pluginBootstrapService.installPackages(
        bootstrapProgress => {
          onProgress?.({
            stage: 'plugin-bootstrap',
            stageIndex: pluginBootstrapStageIndex,
            totalStages,
            progress: bootstrapProgress.progress,
            message: bootstrapProgress.message,
            details: bootstrapProgress.details,
          })
        },
        undefined,
        true
      )

      if (!bootstrapResult.success) {
        return await failUpdate(bootstrapResult.error, 'plugin-bootstrap')
      }

      completedStages.push('plugin-bootstrap')

      // 仅恢复更新前由当前 Electron 实例管理的后端，避免更新操作意外启动服务。
      if (shouldRestartBackend) {
        onProgress?.({
          stage: 'backend',
          stageIndex: backendStageIndex,
          totalStages,
          progress: 0,
          message: '正在重启后端服务...',
        })

        const backendResult = await this.backendService.startBackend()
        if (!backendResult.success) {
          return await failUpdate(backendResult.error, 'backend')
        }
        backendStoppedForUpdate = false

        const status = this.backendService.getStatus()
        onProgress?.({
          stage: 'backend',
          stageIndex: backendStageIndex,
          totalStages,
          progress: 100,
          message: `后端服务已重启，PID: ${status.pid}`,
        })
        completedStages.push('backend')
      }

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
      return await failUpdate(errorMsg)
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

  setBackendService(backendService: BackendService): void {
    this.backendService = backendService
  }

  setTargetBranch(targetBranch: string): void {
    this.targetBranch = targetBranch
  }
}
