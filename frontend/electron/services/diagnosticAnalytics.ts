import { beginMainFeature } from './featureAnalytics'
import type { AnalyticsScriptType } from '../../src/types/analytics'

type ExportResult = {
  success: boolean
  error?: string
  incompleteCount?: number
  skippedPaths?: string[]
}
const reportTypes: Record<string, AnalyticsScriptType> = {
  'maa:exportIssueReport': 'MAA',
  'maaend:exportIssueReport': 'MaaEnd',
  'okww:exportIssueReport': 'Okww',
  'oknte:exportIssueReport': 'OkNte',
  'zzzod:exportIssueReport': 'ZzzOd',
  'bettergi:exportIssueReport': 'BetterGI',
  'whimbox:exportIssueReport': 'Whimbox',
  'maafw:exportIssueReport': 'MaaFW',
  'm9a:exportIssueReport': 'M9A',
  'mss:exportIssueReport': 'MSS',
}
/** 对话框取消与落盘失败分开；只读取结构化结果，不发送附件、路径和错误内容。 */
export async function observeDiagnosticExport<T extends ExportResult>(
  channel: string,
  run: () => Promise<T>
): Promise<T> {
  const telemetry = beginMainFeature('diagnostic_export_finished')
  const props = {
    bundle_kind: channel === 'log:export' ? ('logs' as const) : ('issue' as const),
    script_type: reportTypes[channel] ?? ('none' as const),
  }
  try {
    const result = await run()
    telemetry.finish({
      ...props,
      outcome: result.success ? 'success' : result.error === '用户取消' ? 'cancelled' : 'failure',
      incomplete: result.success
        ? result.incompleteCount === undefined && result.skippedPaths === undefined
          ? 'unknown'
          : (result.incompleteCount ?? result.skippedPaths?.length ?? 0) > 0
            ? 'yes'
            : 'no'
        : 'unknown',
    })
    return result
  } catch (error) {
    telemetry.finish({ ...props, outcome: 'unknown', incomplete: 'unknown' })
    throw error
  }
}
export async function observeDataBackup<T extends ExportResult>(run: () => Promise<T>): Promise<T> {
  const telemetry = beginMainFeature('data_backup_export_finished')
  try {
    const result = await run()
    telemetry.finish({
      outcome: result.success ? 'success' : result.error === '用户取消' ? 'cancelled' : 'failure',
    })
    return result
  } catch (error) {
    telemetry.finish({ outcome: 'unknown' })
    throw error
  }
}
