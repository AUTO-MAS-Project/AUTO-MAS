import { useIssueReport } from './useIssueReport'
import type { ReportLogger } from './useIssueReport'
import { translate as t } from '@/i18n'

const ERROR_KEYS = {
  'no-installation': 'misc.maaIssueReportNoInstallation',
  'no-files': 'misc.maaIssueReportNoFiles',
  'export-failed': 'misc.maaIssueReportFailed',
} as const

export function useMaaIssueReport(logger: ReportLogger) {
  const { exporting, exportIssueReport } = useIssueReport(logger, {
    label: 'MAA',
    fallbackName: 'MAA-logs-*.zip',
    exportFn: async () => {
      const result = await window.electronAPI?.exportMaaIssueReport?.({
        title: t('setting.advanced.exportMaa'),
        zipFilterName: t('misc.zipArchive'),
      })
      if (!result || result.error === '用户取消') return result
      if (result.success)
        return {
          ...result,
          message: t(
            result.incompleteCount ? 'misc.maaIssueReportIncomplete' : 'misc.maaIssueReportSuccess',
            { count: result.collectedCount, incompleteCount: result.incompleteCount }
          ),
        }
      return { ...result, error: t(ERROR_KEYS[result.errorCode ?? 'export-failed']) }
    },
  })
  return { exporting, exportMaaIssueReport: exportIssueReport }
}
