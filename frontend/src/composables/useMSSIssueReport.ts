import { useIssueReport } from './useIssueReport'
import type { ReportLogger } from './useIssueReport'

export function useMSSIssueReport(logger: ReportLogger) {
  const { exporting, exportIssueReport } = useIssueReport(logger, {
    label: 'MSS',
    fallbackName: 'MSS-logs-*.zip',
    exportFn: () => window.electronAPI?.exportMSSIssueReport?.(),
  })
  return { exporting, exportMSSIssueReport: exportIssueReport }
}
