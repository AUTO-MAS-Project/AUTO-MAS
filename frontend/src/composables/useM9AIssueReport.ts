import { useIssueReport } from './useIssueReport'
import type { ReportLogger } from './useIssueReport'

export function useM9AIssueReport(logger: ReportLogger) {
  const { exporting, exportIssueReport } = useIssueReport(logger, {
    label: 'M9A',
    fallbackName: 'M9A-logs-*.zip',
    exportFn: () => window.electronAPI?.exportM9AIssueReport?.(),
  })
  return { exporting, exportM9AIssueReport: exportIssueReport }
}
