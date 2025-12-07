/**
 * 初始化服务 - 统一导出
 * 
 * 使用示例:
 * 
 * ```typescript
 * import { InitializationService } from './services'
 * 
 * const initService = new InitializationService(appRoot, 'dev')
 * 
 * const result = await initService.initialize((progress) => {
 *   console.log(`[${progress.stage}] ${progress.message} - ${progress.progress}%`)
 * })
 * 
 * if (result.success) {
 *   console.log('初始化成功')
 * } else {
 *   console.error('初始化失败:', result.error)
 * }
 * ```
 */

// 镜像源服务
export { MirrorService, MirrorSource, MirrorConfig, CloudMirrorConfig } from './mirrorService'

// 下载服务
export { SmartDownloader, DownloadProgress, ProgressCallback } from './downloadService'

// 镜像源轮替服务
export {
    MirrorRotationService,
    NetworkOperationProgress,
    NetworkOperationCallback,
    MirrorRotationProgress,
    MirrorRotationProgressCallback
} from './mirrorRotationService'

// 环境安装服务
export {
    PythonInstaller,
    PipInstaller,
    GitInstaller,
    EnvironmentCheckResult,
    InstallProgress,
    InstallProgressCallback
} from './environmentService'

// 仓库服务
export {
    RepositoryService,
    RepositoryCheckResult,
    RepositoryProgress,
    RepositoryProgressCallback
} from './repositoryService'

// 依赖服务
export {
    DependencyService,
    DependencyCheckResult,
    DependencyProgress,
    DependencyProgressCallback
} from './dependencyService'

// 初始化总流程服务
export {
    InitializationService,
    InitializationProgress,
    InitializationProgressCallback,
    InitializationResult
} from './initializationService'

// 后端服务
export {
    BackendService,
    BackendStatus,
    BackendStartOptions,
    BackendStatusCallback
} from './backendService'
