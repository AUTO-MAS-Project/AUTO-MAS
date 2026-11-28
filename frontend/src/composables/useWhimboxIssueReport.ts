import { useIssueReport } from '@/composables/useIssueReport'
import type { ReportLogger } from '@/composables/useIssueReport'

export function useWhimboxIssueReport(logger: ReportLogger) {
  const { exporting, exportIssueReport } = useIssueReport(logger, {
    label: 'Whimbox',
    fallbackName: 'Whimbox-logs-*.zip',
    exportFn: () => window.electronAPI?.exportWhimboxIssueReport?.(),
  })
  return { exporting, exportWhimboxIssueReport: exportIssueReport }
}
