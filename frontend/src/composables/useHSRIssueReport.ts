import { useIssueReport } from './useIssueReport'
import type { ReportLogger } from './useIssueReport'

export function useHSRIssueReport(logger: ReportLogger) {
  const { exporting, exportIssueReport } = useIssueReport(logger, {
    label: 'HSR',
    fallbackName: 'HSR-logs-*.zip',
    exportFn: () => window.electronAPI?.exportHSRIssueReport?.(),
  })
  return { exporting, exportHSRIssueReport: exportIssueReport }
}
