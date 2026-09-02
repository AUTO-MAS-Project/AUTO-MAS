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
  RuntimeClientEventMap,
  RuntimeClientOptions,
  RuntimeLogBucket,
  RuntimeLogsByOperation,
  RuntimeMirrorSelection,
  RuntimeRunControl,
  RuntimeRunOptions,
  RuntimeRunResult,
  RuntimeShutdownOptions,
  RuntimeSuperviseHandle,
  RuntimeSuperviseOptions,
  buildRuntimeArgs,
  collectRuntimeLogs,
  createCommandId,
  formatStartupLogs,
  readRuntimeBaseUrl,
  serializeControlCommand,
} from './client'

export {
  RUNTIME_DEVELOPMENT_ROOT_DIRNAME,
  RUNTIME_EXECUTABLE_NAME,
  RUNTIME_EXE_ENV,
  RUNTIME_MODE_ENV,
  PersistedRuntimeLaunchMode,
  RuntimeDisabledLaunchConfig,
  RuntimeLaunchConfig,
  RuntimeLaunchMode,
  RuntimeLaunchModeResolution,
  RuntimeLaunchModeSource,
  RuntimeSupervisedLaunchConfig,
  isPersistedRuntimeLaunchMode,
  resolveDevelopmentRuntimeRoot,
  resolveRuntimeExecutable,
  resolveRuntimeLaunchConfig,
  resolveRuntimeLaunchMode,
  resolveRuntimeLaunchModeDetail,
} from './launchConfig'

export {
  MAX_NDJSON_LINE_LENGTH,
  NdjsonEventStream,
  NdjsonItem,
  parseRuntimeEventLine,
} from './ndjson'

export { RUNTIME_APP_ENV, RUNTIME_TELEMETRY_ENV, buildRuntimeEnv } from './runtimeEnv'

export { CreateRuntimeClientOptions, createRuntimeClient } from './runtimeClientFactory'

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
  RuntimeCapability,
  RuntimeClientError,
  RuntimeClientErrorCode,
  RuntimeClientErrorDefinition,
  RuntimeClientErrorDetails,
  RuntimeCode,
  RuntimeControlCommand,
  RuntimeControlKind,
  RuntimeErrorDefinition,
  RuntimeErrorEvent,
  RuntimeEvent,
  RuntimeEventCommon,
  RuntimeEventType,
  RuntimeHelloEvent,
  RuntimeKnownCapability,
  RuntimeKnownErrorCode,
  RuntimeKnownProgressStatus,
  RuntimeKnownRemediation,
  RuntimeKnownStage,
  RuntimeKnownStateStatus,
  RuntimeLogEvent,
  RuntimeProgressEvent,
  RuntimeProgressStatus,
  RuntimeRemediation,
  RuntimeResultEvent,
  RuntimeResultStatus,
  RuntimeStage,
  RuntimeStateEvent,
  RuntimeStateStatus,
  RuntimeWarningEvent,
  RuntimeWarningSummary,
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
