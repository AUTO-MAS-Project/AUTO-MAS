/**
 * 初始化总流程服务
 * 重构版本 - 协调所有初始化步骤
 */

import { MirrorService } from './mirrorService'
import { PythonInstaller, PipInstaller, GitInstaller } from './environmentService'
import { RepositoryService } from './repositoryService'
import { DependencyService } from './dependencyService'
import { BackendService } from './backendService'

// 导入日志服务
import { logService } from './logService'

// 使用日志服务的日志记录器
const logger = {
    error: (message: string, ...args: any[]) => logService.error('初始化服务', `${message} ${args.length > 0 ? JSON.stringify(args) : ''}`),
    warn: (message: string, ...args: any[]) => logService.warn('初始化服务', `${message} ${args.length > 0 ? JSON.stringify(args) : ''}`),
    info: (message: string, ...args: any[]) => logService.info('初始化服务', `${message} ${args.length > 0 ? JSON.stringify(args) : ''}`),
    debug: (message: string, ...args: any[]) => logService.debug('初始化服务', `${message} ${args.length > 0 ? JSON.stringify(args) : ''}`),
    log: (message: string, ...args: any[]) => logService.info('初始化服务', `${message} ${args.length > 0 ? JSON.stringify(args) : ''}`)
}

// ==================== 类型定义 ====================

export interface InitializationProgress {
    stage: 'mirror' | 'python' | 'pip' | 'git' | 'repository' | 'dependency' | 'backend' | 'complete'
    stageIndex: number
    totalStages: number
    progress: number
    message: string
    details?: {
        checkInfo?: any  // 可以是 EnvironmentCheckResult, RepositoryCheckResult, 或 DependencyCheckResult
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
        this.backendService = new BackendService(appRoot)
        this.targetBranch = targetBranch
    }

    /**
     * 执行完整的初始化流程
     */
    async initialize(onProgress?: InitializationProgressCallback, startBackend: boolean = true): Promise<InitializationResult> {
        const completedStages: string[] = []
        const totalStages = startBackend ? 7 : 6

        try {
            // 阶段 1: 初始化镜像源配置
            onProgress?.({
                stage: 'mirror',
                stageIndex: 1,
                totalStages,
                progress: 0,
                message: '正在初始化镜像源配置...'
            })

            await this.mirrorService.initialize()
            completedStages.push('mirror')

            onProgress?.({
                stage: 'mirror',
                stageIndex: 1,
                totalStages,
                progress: 100,
                message: '镜像源配置初始化完成'
            })

            // 阶段 2: 安装 Python
            onProgress?.({
                stage: 'python',
                stageIndex: 2,
                totalStages,
                progress: 0,
                message: '正在安装 Python...'
            })

            const pythonInstaller = new PythonInstaller(this.appRoot, this.mirrorService)
            const pythonResult = await pythonInstaller.install((installProgress) => {
                onProgress?.({
                    stage: 'python',
                    stageIndex: 2,
                    totalStages,
                    progress: installProgress.progress,
                    message: installProgress.message,
                    details: installProgress.details
                })
            })

            if (!pythonResult.success) {
                return {
                    success: false,
                    error: pythonResult.error,
                    completedStages,
                    failedStage: 'python'
                }
            }

            completedStages.push('python')

            // 阶段 3: 安装 Pip
            onProgress?.({
                stage: 'pip',
                stageIndex: 3,
                totalStages,
                progress: 0,
                message: '正在安装 Pip...'
            })

            const pipInstaller = new PipInstaller(this.appRoot, this.mirrorService)
            const pipResult = await pipInstaller.install((installProgress) => {
                onProgress?.({
                    stage: 'pip',
                    stageIndex: 3,
                    totalStages,
                    progress: installProgress.progress,
                    message: installProgress.message,
                    details: installProgress.details
                })
            })

            if (!pipResult.success) {
                return {
                    success: false,
                    error: pipResult.error,
                    completedStages,
                    failedStage: 'pip'
                }
            }

            completedStages.push('pip')

            // 阶段 4: 安装 Git
            onProgress?.({
                stage: 'git',
                stageIndex: 4,
                totalStages,
                progress: 0,
                message: '正在安装 Git...'
            })

            const gitInstaller = new GitInstaller(this.appRoot, this.mirrorService)
            const gitResult = await gitInstaller.install((installProgress) => {
                onProgress?.({
                    stage: 'git',
                    stageIndex: 4,
                    totalStages,
                    progress: installProgress.progress,
                    message: installProgress.message,
                    details: installProgress.details
                })
            })

            if (!gitResult.success) {
                return {
                    success: false,
                    error: gitResult.error,
                    completedStages,
                    failedStage: 'git'
                }
            }

            completedStages.push('git')

            // 阶段 5: 拉取源码
            onProgress?.({
                stage: 'repository',
                stageIndex: 5,
                totalStages,
                progress: 0,
                message: '正在拉取源码...'
            })

            const repositoryService = new RepositoryService(this.appRoot, this.mirrorService, this.targetBranch)
            const repoResult = await repositoryService.pullRepository((repoProgress) => {
                onProgress?.({
                    stage: 'repository',
                    stageIndex: 5,
                    totalStages,
                    progress: repoProgress.progress,
                    message: repoProgress.message,
                    details: repoProgress.details
                })
            })

            if (!repoResult.success) {
                return {
                    success: false,
                    error: repoResult.error,
                    completedStages,
                    failedStage: 'repository'
                }
            }

            completedStages.push('repository')

            // 阶段 6: 安装依赖
            onProgress?.({
                stage: 'dependency',
                stageIndex: 6,
                totalStages,
                progress: 0,
                message: '正在安装依赖...'
            })

            const dependencyService = new DependencyService(this.appRoot, this.mirrorService)
            const depResult = await dependencyService.installDependencies((depProgress) => {
                onProgress?.({
                    stage: 'dependency',
                    stageIndex: 6,
                    totalStages,
                    progress: depProgress.progress,
                    message: depProgress.message,
                    details: depProgress.details
                })
            })

            if (!depResult.success) {
                return {
                    success: false,
                    error: depResult.error,
                    completedStages,
                    failedStage: 'dependency'
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
                    message: '正在启动后端服务...'
                })

                const backendResult = await this.backendService.startBackend()

                if (!backendResult.success) {
                    return {
                        success: false,
                        error: backendResult.error,
                        completedStages,
                        failedStage: 'backend'
                    }
                }

                const status = this.backendService.getStatus()
                onProgress?.({
                    stage: 'backend',
                    stageIndex: 7,
                    totalStages,
                    progress: 100,
                    message: `后端服务已启动，PID: ${status.pid}`
                })

                completedStages.push('backend')
            }

            // 完成
            onProgress?.({
                stage: 'complete',
                stageIndex: totalStages,
                totalStages,
                progress: 100,
                message: '初始化完成'
            })

            return {
                success: true,
                completedStages
            }
        } catch (error) {
            const errorMsg = error instanceof Error ? error.message : String(error)
            logger.error('初始化失败:', errorMsg)

            return {
                success: false,
                error: errorMsg,
                completedStages
            }
        }
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
                message: '正在更新源码...'
            })

            const repositoryService = new RepositoryService(this.appRoot, this.mirrorService, this.targetBranch)
            const repoResult = await repositoryService.pullRepository((repoProgress) => {
                onProgress?.({
                    stage: 'repository',
                    stageIndex: 1,
                    totalStages,
                    progress: repoProgress.progress,
                    message: repoProgress.message,
                    details: repoProgress.details
                })
            })

            if (!repoResult.success) {
                return {
                    success: false,
                    error: repoResult.error,
                    completedStages,
                    failedStage: 'repository'
                }
            }

            completedStages.push('repository')

            // 阶段 2: 安装依赖
            onProgress?.({
                stage: 'dependency',
                stageIndex: 2,
                totalStages,
                progress: 0,
                message: '正在更新依赖...'
            })

            const dependencyService = new DependencyService(this.appRoot, this.mirrorService)
            const depResult = await dependencyService.installDependencies((depProgress) => {
                onProgress?.({
                    stage: 'dependency',
                    stageIndex: 2,
                    totalStages,
                    progress: depProgress.progress,
                    message: depProgress.message,
                    details: depProgress.details
                })
            })

            if (!depResult.success) {
                return {
                    success: false,
                    error: depResult.error,
                    completedStages,
                    failedStage: 'dependency'
                }
            }

            completedStages.push('dependency')

            // 完成
            onProgress?.({
                stage: 'complete',
                stageIndex: totalStages,
                totalStages,
                progress: 100,
                message: '更新完成'
            })

            return {
                success: true,
                completedStages
            }
        } catch (error) {
            const errorMsg = error instanceof Error ? error.message : String(error)
            logger.error('更新失败:', errorMsg)

            return {
                success: false,
                error: errorMsg,
                completedStages
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
