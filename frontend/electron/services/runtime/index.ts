/**
 * AUTO-MAS Runtime 客户端 - 统一导出
 *
 * 使用示例：
 *
 * ```typescript
 * import { RuntimeClient } from './runtime'
 *
 * const client = new RuntimeClient({
 *   runtimePath,
 *   appRoot,
 *   env: { AUTO_MAS_TELEMETRY: 'disabled' },
 * })
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
  DEFAULT_RESULT_SETTLE_TIMEOUT_MS,
  DEFAULT_SHUTDOWN_TIMEOUT_MS,
  RuntimeClient,
  RuntimeClientEventMap,
  RuntimeClientOptions,
  RuntimeLogBucket,
  RuntimeLogsByOperation,
  RuntimeMirrorSelection,
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
  RUNTIME_EXECUTABLE_NAME,
  RUNTIME_EXE_ENV,
  RUNTIME_MODE_ENV,
  RuntimeLaunchConfig,
  RuntimeLaunchMode,
  resolveRuntimeExecutable,
  resolveRuntimeLaunchConfig,
  resolveRuntimeLaunchMode,
} from './launchConfig'

export { NdjsonEventStream, NdjsonItem, parseRuntimeEventLine } from './ndjson'

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
