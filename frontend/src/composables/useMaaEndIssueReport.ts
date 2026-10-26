import { translate as t } from '@/i18n'
import { useIssueReport } from './useIssueReport'
import type { ReportLogger } from './useIssueReport'

export function useMaaEndIssueReport(logger: ReportLogger) {
  const { exporting, exportIssueReport } = useIssueReport(logger, {
    label: 'MaaEnd',
    fallbackName: 'MaaEnd-logs-*.zip',
    exportFn: async () => {
      const result = await window.electronAPI?.exportMaaEndIssueReport?.()
      return result?.success ? { ...result, message: t('misc.maaendLogFoldersOpened') } : result
    },
  })
  return { exporting, exportMaaEndIssueReport: exportIssueReport }
}
