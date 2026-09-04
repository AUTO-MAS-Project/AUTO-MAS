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
  MirrorRotationProgressCallback,
} from './mirrorRotationService'

// 环境安装服务
export {
  PythonInstaller,
  PipInstaller,
  GitInstaller,
  EnvironmentCheckResult,
  InstallProgress,
  InstallProgressCallback,
} from './environmentService'

// 仓库服务
export {
  RepositoryService,
  RepositoryCheckResult,
  RepositoryProgress,
  RepositoryProgressCallback,
} from './repositoryService'

// 依赖服务
export {
  DependencyService,
  DependencyCheckResult,
  DependencyProgress,
  DependencyProgressCallback,
} from './dependencyService'

// 初始化总流程服务
export {
  InitializationService,
  InitializationProgress,
  InitializationProgressCallback,
  InitializationResult,
} from './initializationService'

// Runtime 初始化链路（灰度开关打开后顶掉五步安装链）
export {
  BootstrapProgressBridge,
  BootstrapProgressUpdate,
  CriticalFilesCheck,
  InitializationRunStage,
  InitializationStage,
  InitializationStageStatus,
  RuntimeDoctorCheck,
  RuntimeInitializationService,
  RuntimeRetryMode,
  RuntimeStageOutcome,
  mapDoctorChecksToCriticalFiles,
  mapMirrorSelection,
  mapRuntimeStage,
  toRuntimeVersion,
} from './runtimeInitializationService'

// Runtime 后端更新链路（停机 → bootstrap → 重新监督）
export {
  BackendUpdateController,
  RuntimeUpdateDependencies,
  RuntimeUpdateOutcome,
  RuntimeUpdatePhase,
  RuntimeUpdateProgress,
  RuntimeUpdateRetryAction,
  RuntimeUpdateStage,
  cancelBackendUpdate,
  describeRetryAction,
  normalizeRuntimeUpdateVersion,
  resetRuntimeUpdateSession,
  resolveRetryActions,
  retryBackendUpdate,
  updateBackendViaRuntime,
} from './runtimeUpdateService'

// 后端服务
export {
  BackendService,
  BackendStatus,
  BackendStartOptions,
  BackendStatusCallback,
} from './backendService'

// AUTO-MAS Runtime 客户端（NDJSON 协议 v1）
export {
  RuntimeClient,
  RuntimeClientError,
  RuntimeClientErrorCode,
  RuntimeClientOptions,
  RuntimeEvent,
  RuntimeHelloEvent,
  RuntimeLogsByOperation,
  RuntimeProgressEvent,
  RuntimeResultEvent,
  RuntimeRunOptions,
  RuntimeRunResult,
  RuntimeStateEvent,
  RuntimeSuperviseHandle,
  RuntimeSuperviseOptions,
  formatStartupLogs,
  isRuntimeClientError,
} from './runtime'
