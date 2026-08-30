import { useIssueReport } from './useIssueReport'
import type { ReportLogger } from './useIssueReport'

export function useOkwwIssueReport(logger: ReportLogger) {
  const { exporting, exportIssueReport } = useIssueReport(logger, {
    label: 'OK-WW',
    fallbackName: 'OK-WW-logs-*.zip',
    exportFn: () => window.electronAPI?.exportOkwwIssueReport?.(),
  })
  return { exporting, exportOkwwIssueReport: exportIssueReport }
}
