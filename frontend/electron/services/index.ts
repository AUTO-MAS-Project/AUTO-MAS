/**
 * 初始化服务 - 统一导出
 *
 * 使用示例:
 *
 * ```typescript
 * import { InitializationService } from './services'
 *
 * const initService = new InitializationService(appRoot)
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

// 下载服务
export { SmartDownloader, type DownloadProgress, type ProgressCallback } from './downloadService'

// 初始化总流程服务
export {
  InitializationService,
  type InitializationProgress,
  type InitializationProgressCallback,
  type InitializationResult,
} from './initializationService'

// Runtime 初始化与失败恢复
export {
  BootstrapProgressBridge,
  type BootstrapProgressUpdate,
  type CriticalFilesCheck,
  type InitializationRunStage,
  type InitializationStage,
  type InitializationStageStatus,
  type RuntimeDoctorCheck,
  RuntimeInitializationService,
  type RuntimeRetryMode,
  type RuntimeStageOutcome,
  mapDoctorChecksToCriticalFiles,
  mapRuntimeStage,
  toRuntimeVersion,
} from './runtimeInitializationService'

// Runtime 线上最新版本解析
export {
  RUNTIME_RELEASE_CACHE_TTL_MS,
  RUNTIME_RELEASE_FETCH_TIMEOUT_MS,
  RUNTIME_RELEASE_REPO,
  RUNTIME_VERSION_PATTERN,
  type LatestRuntimeVersionLookup,
  type ResolveLatestRuntimeVersionOptions,
  type RuntimeReleaseChannel,
  type RuntimeReleaseFetcher,
  type RuntimeReleaseSource,
  buildRuntimeReleaseSources,
  isNewerRuntimeVersion,
  parseRuntimeReleaseList,
  resetLatestRuntimeVersionCache,
  resolveLatestRuntimeVersion,
  resolveLatestRuntimeVersionCached,
  resolveRuntimeReleaseChannel,
  selectLatestRuntimeVersion,
} from './runtimeReleaseService'

// Runtime 可执行文件对齐到线上最新版
export {
  RUNTIME_BINARY_ALIGN_ERROR,
  RUNTIME_BINARY_CANCELLED,
  RUNTIME_BINARY_DOWNLOAD_FAILED,
  RUNTIME_BINARY_REPLACE_FAILED,
  RUNTIME_LATEST_UNAVAILABLE,
  RUNTIME_TEXT_FETCH_TIMEOUT_MS,
  type LatestRuntimeVersionResolver,
  type RuntimeBinaryAlignOptions,
  type RuntimeBinaryAlignResult,
  type RuntimeBinaryAlignStatus,
  type RuntimeBinarySource,
  type RuntimeBinarySyncOptions,
  type RuntimeBinarySyncProgress,
  type RuntimeBinarySyncResult,
  type RuntimeBinarySyncStatus,
  type RuntimeBinaryTarget,
  type RuntimeTextSource,
  type TrustedRuntimeHashLookup,
  alignRuntimeBinaryWithLatest,
  buildRuntimeBinarySources,
  buildRuntimeSumsSources,
  fetchTrustedRuntimeHash,
  hashFileSha256,
  syncRuntimeBinary,
} from './runtimeBinaryService'

// Runtime 后端更新链路（停机 → bootstrap → 重新监督）
export {
  type BackendUpdateController,
  type RuntimeUpdateDependencies,
  type RuntimeUpdateOutcome,
  type RuntimeUpdatePhase,
  type RuntimeUpdateProgress,
  type RuntimeUpdateRetryAction,
  type RuntimeUpdateStage,
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
  type BackendStatus,
  type BackendStartOptions,
  type BackendStatusCallback,
} from './backendService'

// AUTO-MAS Runtime 客户端（NDJSON 协议 v1）
export {
  RuntimeClient,
  RuntimeClientError,
  type RuntimeClientErrorCode,
  type RuntimeClientOptions,
  type RuntimeEvent,
  type RuntimeHelloEvent,
  type RuntimeLogsByOperation,
  type RuntimeProgressEvent,
  type RuntimeResultEvent,
  type RuntimeRunOptions,
  type RuntimeRunResult,
  type RuntimeStateEvent,
  type RuntimeSuperviseHandle,
  type RuntimeSuperviseOptions,
  formatStartupLogs,
  isRuntimeClientError,
} from './runtime'
