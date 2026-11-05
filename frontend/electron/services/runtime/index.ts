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
  RuntimeClient,
  RuntimeMirrorSelection,
  RuntimeRunControl,
  RuntimeRunOptions,
  RuntimeRunResult,
  RuntimeSuperviseHandle,
  formatStartupLogs,
  readRuntimeBaseUrl,
} from './client'

export {
  RUNTIME_BACKUP_SUFFIX,
  RUNTIME_EXECUTABLE_NAME,
  RUNTIME_EXE_ENV,
  RUNTIME_MODE_ENV,
  PersistedRuntimeLaunchMode,
  RuntimeLaunchMode,
  RuntimeLaunchConfig,
  isPersistedRuntimeLaunchMode,
  recoverRuntimeBackup,
  resolveRuntimeLaunchConfig,
  resolveRuntimeLaunchMode,
  resolveRuntimeLaunchModeDetail,
} from './launchConfig'

export { CreateRuntimeClientOptions, createRuntimeClient } from './runtimeClientFactory'

export {
  RUNTIME_CLIENT_ERROR_DEFINITIONS,
  RuntimeEvent,
  RuntimeLogEvent,
  RuntimeProgressEvent,
  RuntimeRemediation,
  RuntimeStage,
  isRuntimeClientError,
} from './protocol'
