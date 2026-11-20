import { analyticsService } from './analyticsService'
import { analyticsDuration } from './analyticsPolicy'
import { startupAttempt, localStartupAttempt, inStartupOperation } from './startupHardware/monitor'
import type {
  AnalyticsInitializationCode,
  AnalyticsInitializationStage,
  AnalyticsRuntimeMode,
} from '../../src/types/analytics'

const codes = new Set<AnalyticsInitializationCode>([
  'RUNTIME_NOT_FOUND',
  'RUNTIME_BINARY_ALIGN_ERROR',
  'OPERATION_CANCELLED',
  'NETWORK_UNAVAILABLE',
  'DEPENDENCY_SYNC_FAILED',
  'ENVIRONMENT_BROKEN',
  'PYTHON_VERSION_MISMATCH',
  'LOCKFILE_MISSING',
  'LOCKFILE_OUTDATED',
  'WORKSPACE_RESTORE_FAILED',
  'INTERNAL_ERROR',
])
const stages = new Set([
  'runtime_binary',
  'bootstrap',
  'python',
  'pip',
  'git',
  'repository',
  'dependency',
])

/** 只观察实际命令返回；不把进度、跳过或 Runtime 接管标记算作执行成功。 */
export async function observeInitializationStage<
  T extends {
    success: boolean
    code?: string
    failedStage?: string
  },
>(
  stage: AnalyticsInitializationStage,
  runtimeMode: AnalyticsRuntimeMode,
  run: () => Promise<T>
): Promise<T> {
  const context = analyticsService.getContext()
  const attempt = localStartupAttempt()
  const stopStage = attempt?.beginStage(stage)
  const startedAt = performance.now()
  const finish = (result?: T) => {
    const outcome = result?.success
      ? 'success'
      : result?.code === 'OPERATION_CANCELLED'
        ? 'cancelled'
        : 'failure'
    const code: AnalyticsInitializationCode = result?.success
      ? 'none'
      : codes.has(result?.code as AnalyticsInitializationCode)
        ? (result!.code as AnalyticsInitializationCode)
        : 'unknown'
    const summary = stopStage?.(outcome, code)
    if (
      attempt &&
      attempt === startupAttempt() &&
      outcome === 'failure' &&
      (stage === 'runtime_binary' || code === 'RUNTIME_NOT_FOUND')
    )
      attempt.reportHostFailure?.(stage, code)
    analyticsService.recordMainEvent(
      context,
      {
        name: 'initialization_stage_finished_v2',
        props: {
          stage,
          runtime_mode: runtimeMode,
          outcome,
          known_code: code,
          failed_stage: result?.success
            ? 'none'
            : stage === 'runtime_binary'
              ? 'runtime_binary'
              : stages.has(result?.failedStage ?? '')
                ? (result!.failedStage as AnalyticsInitializationStage)
                : 'unknown',
          duration_bucket: analyticsDuration(performance.now() - startedAt),
        },
      },
      attempt === startupAttempt() ? summary : undefined
    )
  }
  try {
    const result = await inStartupOperation(run)
    finish(result)
    return result
  } catch (error) {
    finish()
    throw error
  }
}
