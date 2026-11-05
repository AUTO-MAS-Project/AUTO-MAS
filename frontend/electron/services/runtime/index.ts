/**
 * AUTO-MAS Runtime 客户端 - 统一导出
 *
 * 使用示例：
 *
 * ```typescript
 * import { createRuntimeClient } from './runtime'
 *
 * // 遥测开关（AUTO_MAS_TELEMETRY）由 createRuntimeClient 统一注入，不需要调用方自己判断；
 * // 显式传 env 仍可覆盖它。
 * const client = createRuntimeClient({ runtimePath, appRoot })
 *
 * const outcome = await client.run(['doctor'], {
 *   onProgress: event => console.log(event.stage, event.status, event.message),
 * })
 *
 * if (!outcome.success) {
 *   // 精确原因读 result.code，不要读退出码，也不要解析 message
 *   console.error(outcome.code, outcome.result.remediation)
 * }
 * ```
 */

export {
  DEFAULT_HANDSHAKE_TIMEOUT_MS,
  DEFAULT_RECENT_LOG_CAPACITY,
  DEFAULT_RESULT_SETTLE_TIMEOUT_MS,
  DEFAULT_SHUTDOWN_TIMEOUT_MS,
  RuntimeClient,
  type RuntimeClientEventMap,
  type RuntimeClientOptions,
  type RuntimeLogBucket,
  type RuntimeLogsByOperation,
  type RuntimeMirrorSelection,
  type RuntimeRunControl,
  type RuntimeRunOptions,
  type RuntimeRunResult,
  type RuntimeShutdownOptions,
  type RuntimeSuperviseHandle,
  type RuntimeSuperviseOptions,
  buildRuntimeArgs,
  collectRuntimeLogs,
  createCommandId,
  formatStartupLogs,
  readRuntimeBaseUrl,
  readRuntimeWarningSummaries,
  serializeControlCommand,
} from './client'

export {
  RUNTIME_BACKUP_SUFFIX,
  RUNTIME_DEVELOPMENT_ROOT_DIRNAME,
  RUNTIME_EXECUTABLE_NAME,
  RUNTIME_EXE_ENV,
  RUNTIME_MODE_ENV,
  type PersistedRuntimeLaunchMode,
  type RuntimeLaunchMode,
  type RuntimeLaunchModeResolution,
  type RuntimeLaunchModeSource,
  type RuntimeLaunchConfig,
  isPersistedRuntimeLaunchMode,
  recoverRuntimeBackup,
  resolveDevelopmentRuntimeRoot,
  resolveRuntimeExecutable,
  resolveRuntimeLaunchConfig,
  resolveRuntimeLaunchMode,
  resolveRuntimeLaunchModeDetail,
} from './launchConfig'

export {
  MAX_NDJSON_LINE_LENGTH,
  NdjsonEventStream,
  type NdjsonItem,
  parseRuntimeEventLine,
} from './ndjson'

export { RUNTIME_APP_ENV, RUNTIME_TELEMETRY_ENV, buildRuntimeEnv } from './runtimeEnv'

export { type CreateRuntimeClientOptions, createRuntimeClient } from './runtimeClientFactory'

export {
  RUNTIME_CAPABILITIES,
  RUNTIME_CLIENT_ERROR_DEFINITIONS,
  RUNTIME_ERROR_CODES,
  RUNTIME_EXIT_CODES,
  RUNTIME_OK_CODE,
  RUNTIME_PROGRESS_STATUSES,
  RUNTIME_PROTOCOL_VERSION,
  RUNTIME_REMEDIATIONS,
  RUNTIME_STAGES,
  RUNTIME_STATE_STATUSES,
  type RuntimeCapability,
  RuntimeClientError,
  type RuntimeClientErrorCode,
  type RuntimeClientErrorDefinition,
  type RuntimeClientErrorDetails,
  type RuntimeCode,
  type RuntimeControlCommand,
  type RuntimeControlKind,
  type RuntimeErrorDefinition,
  type RuntimeErrorEvent,
  type RuntimeEvent,
  type RuntimeEventCommon,
  type RuntimeEventType,
  type RuntimeHelloEvent,
  type RuntimeKnownCapability,
  type RuntimeKnownErrorCode,
  type RuntimeKnownProgressStatus,
  type RuntimeKnownRemediation,
  type RuntimeKnownStage,
  type RuntimeKnownStateStatus,
  type RuntimeLogEvent,
  type RuntimeProgressEvent,
  type RuntimeProgressStatus,
  type RuntimeRemediation,
  type RuntimeResultEvent,
  type RuntimeResultStatus,
  type RuntimeStage,
  type RuntimeStateEvent,
  type RuntimeStateStatus,
  type RuntimeWarningEvent,
  type RuntimeWarningSummary,
  isKnownRuntimeCapability,
  isKnownRuntimeCode,
  isKnownRuntimeProgressStatus,
  isKnownRuntimeRemediation,
  isKnownRuntimeStage,
  isKnownRuntimeStateStatus,
  isRetryableRuntimeCode,
  isRuntimeClientError,
  isRuntimeResultEvent,
  lookupRuntimeErrorDefinition,
} from './protocol'
